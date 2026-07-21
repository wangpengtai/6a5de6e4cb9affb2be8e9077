# -*- coding: utf-8 -*-
"""FastAPI 主入口 - 初始化、路由挂载、生命周期管理"""

import asyncio
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import ConfigManager
from app.logger import get_logger, setup_logger
from app.video import MjpegProxy
from app.recorder import Recorder
from app.voice import VoiceSpeaker
from app.ai import AiAnalyzer
from app import routes_api, routes_page

logger = get_logger("MAIN")

# 全局组件
mjpeg_proxy: MjpegProxy = None
recorder: Recorder = None
voice_speaker: VoiceSpeaker = None
ai_analyzer: AiAnalyzer = None
disk_check_timer: threading.Timer = None


def _on_camera_disconnect():
    """摄像头断开回调"""
    logger.warning("摄像头已断开")
    if voice_speaker:
        voice_speaker.speak("摄像头已断开连接")


def _on_camera_reconnect():
    """摄像头重连回调"""
    logger.info("摄像头已重连")
    if voice_speaker:
        voice_speaker.speak("摄像头已重新连接")


def _on_camera_status_change(status: str):
    """摄像头状态变化回调"""
    logger.info(f"摄像头状态变化: {status}")


def _check_disk_space():
    """定时检查磁盘空间"""
    global disk_check_timer
    try:
        if recorder:
            disk_info = recorder.get_disk_info()
            config = ConfigManager().config.storage
            if disk_info.get("free_mb", 0) < config.min_free_space_mb:
                logger.warning(f"磁盘空间不足: {disk_info.get('free_mb')}MB")
                if voice_speaker:
                    voice_speaker.speak("磁盘空间不足，请注意清理")
    except Exception as e:
        logger.error(f"磁盘检查异常: {e}")
    finally:
        # 每60秒检查一次
        disk_check_timer = threading.Timer(60, _check_disk_space)
        disk_check_timer.daemon = True
        disk_check_timer.start()


def _record_frame_writer():
    """后台线程：从 MjpegProxy 获取帧并写入录像"""
    while mjpeg_proxy and mjpeg_proxy._running:
        try:
            if recorder and recorder.recording:
                frame = mjpeg_proxy.get_latest_frame()
                if frame:
                    recorder.write_frame(frame)
            time.sleep(1.0 / ConfigManager().config.storage.fps)
        except Exception as e:
            logger.error(f"录像写帧异常: {e}")
            time.sleep(0.1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动和关闭"""
    global mjpeg_proxy, recorder, voice_speaker, ai_analyzer, disk_check_timer

    # ─── 启动初始化 ───
    logger.info("正在初始化系统...")

    # 初始化配置
    config_mgr = ConfigManager()
    config = config_mgr.config

    # 初始化录像管理器
    recorder = Recorder()

    # 初始化语音播报
    voice_speaker = VoiceSpeaker()
    voice_speaker.start()

    # 初始化 MJPEG 视频流代理
    cam_cfg = config.camera
    mjpeg_proxy = MjpegProxy(
        url=cam_cfg.url,
        reconnect_interval_ms=cam_cfg.reconnect_interval_ms,
        network_timeout_ms=cam_cfg.network_timeout_ms,
        on_status_change=_on_camera_status_change,
        on_disconnect=_on_camera_disconnect,
        on_reconnect=_on_camera_reconnect,
    )
    mjpeg_proxy.start()

    # 初始化 AI 分析
    ai_analyzer = AiAnalyzer(get_frame_func=mjpeg_proxy.get_latest_frame)

    # 注入路由依赖
    routes_api.init_routes(mjpeg_proxy, recorder, voice_speaker, ai_analyzer)

    # 启动录像写帧线程
    frame_thread = threading.Thread(target=_record_frame_writer, daemon=True)
    frame_thread.start()

    # 启动磁盘检查定时器
    disk_check_timer = threading.Timer(60, _check_disk_space)
    disk_check_timer.daemon = True
    disk_check_timer.start()

    # 启动 AI 分析（如果启用）
    ai_analyzer.start()

    logger.info("系统初始化完成")
    yield

    # ─── 关闭清理 ───
    logger.info("正在关闭系统...")

    # 停止 AI 分析
    if ai_analyzer:
        ai_analyzer.stop()

    # 停止磁盘检查
    if disk_check_timer:
        disk_check_timer.cancel()

    # 停止录像
    if recorder and recorder.recording:
        recorder.stop_recording()

    # 停止视频流
    if mjpeg_proxy:
        mjpeg_proxy.stop()

    # 停止语音
    if voice_speaker:
        voice_speaker.stop()

    logger.info("系统已关闭")


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例"""
    # 初始化日志
    setup_logger("app")

    app = FastAPI(
        title="Packing Monitor",
        description="Packing Monitor Backend API",
        version="1.0.0",
        lifespan=lifespan,
    )

    # 挂载静态文件目录
    static_dir = Path(__file__).parent.parent / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # 挂载 API 路由
    app.include_router(routes_api.router)

    # 挂载页面路由
    app.include_router(routes_page.router)

    return app


# 创建应用实例
app = create_app()
