# -*- coding: utf-8 -*-
"""API 路由模块 - 所有 REST API 和 WebSocket 端点"""

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.responses import StreamingResponse, FileResponse

from app.config import ConfigManager
from app.logger import get_logger
from app.video import MjpegProxy
from app.recorder import Recorder
from app.voice import VoiceSpeaker
from app.ai import AiAnalyzer

logger = get_logger("API")

router = APIRouter(prefix="/api")

# 全局引用（由 main.py 注入）
mjpeg_proxy: Optional[MjpegProxy] = None
recorder: Optional[Recorder] = None
voice_speaker: Optional[VoiceSpeaker] = None
ai_analyzer: Optional[AiAnalyzer] = None

# WebSocket 管理器
_ws_clients: list[WebSocket] = []
_ws_lock = asyncio.Lock()


def init_routes(proxy: MjpegProxy, rec: Recorder, voice: VoiceSpeaker, ai: AiAnalyzer):
    """初始化路由，注入全局依赖"""
    global mjpeg_proxy, recorder, voice_speaker, ai_analyzer
    mjpeg_proxy = proxy
    recorder = rec
    voice_speaker = voice
    ai_analyzer = ai


# ─── 系统状态 ───

@router.get("/status")
async def get_status():
    """获取系统状态：摄像头连接、录像状态、磁盘空间"""
    cam_status = mjpeg_proxy.get_status() if mjpeg_proxy else {"connected": False, "url": ""}
    disk_info = recorder.get_disk_info() if recorder else {}
    return {
        "camera": cam_status,
        "recording": recorder.recording if recorder else False,
        "platform": recorder.current_platform if recorder else "",
        "waybill": recorder.current_waybill if recorder else "",
        "disk": disk_info,
        "ai_enabled": ai_analyzer.enabled if ai_analyzer else False,
    }


# ─── 录像控制 ───

@router.post("/record/start")
async def start_record():
    """开始录像"""
    if not recorder:
        raise HTTPException(status_code=500, detail="录像模块未初始化")
    if not mjpeg_proxy or not mjpeg_proxy.connected:
        raise HTTPException(status_code=400, detail="摄像头未连接")
    fps = ConfigManager().config.storage.fps
    ok = recorder.start_recording(fps=fps)
    if not ok:
        raise HTTPException(status_code=500, detail="录像启动失败")
    # 语音播报
    if voice_speaker:
        voice_speaker.speak("录像已开始")
    # 通知 WebSocket 客户端
    await _broadcast_status()
    return {"ok": True, "message": "录像已开始"}


@router.post("/record/stop")
async def stop_record():
    """停止录像"""
    if not recorder:
        raise HTTPException(status_code=500, detail="录像模块未初始化")
    filepath = recorder.stop_recording()
    if voice_speaker:
        voice_speaker.speak("录像已停止")
    await _broadcast_status()
    return {"ok": True, "message": "录像已停止", "filepath": filepath}


@router.post("/record/bind")
async def bind_waybill(data: dict):
    """绑定运单号：{platform, waybill}"""
    if not recorder:
        raise HTTPException(status_code=500, detail="录像模块未初始化")
    platform = data.get("platform", "other")
    waybill = data.get("waybill", "")
    if not waybill:
        raise HTTPException(status_code=400, detail="运单号不能为空")
    recorder.bind_waybill(platform, waybill)
    if voice_speaker:
        voice_speaker.speak(f"已绑定运单号 {waybill}")
    await _broadcast_status()
    return {"ok": True, "message": f"已绑定: 平台={platform}, 运单号={waybill}"}


# ─── 截图 ───

@router.post("/screenshot")
async def take_screenshot():
    """截取当前帧并保存"""
    if not mjpeg_proxy or not recorder:
        raise HTTPException(status_code=500, detail="模块未初始化")
    frame = mjpeg_proxy.get_latest_frame()
    if not frame:
        raise HTTPException(status_code=400, detail="无可用视频帧")
    filepath = recorder.save_screenshot(frame)
    if not filepath:
        raise HTTPException(status_code=500, detail="截图保存失败")
    return {"ok": True, "filepath": filepath}


# ─── 视频流 ───

@router.get("/stream")
async def video_stream():
    """MJPEG 视频流端点"""
    if not mjpeg_proxy:
        raise HTTPException(status_code=500, detail="视频流模块未初始化")
    return StreamingResponse(
        mjpeg_proxy.stream_generator(),
        media_type="multipart/x-mixed-replace; boundary=--frameboundary",
    )


# ─── 文件管理 ───

@router.get("/files")
async def list_files(
    platform: Optional[str] = Query(None),
    waybill: Optional[str] = Query(None),
    type: Optional[str] = Query("all"),
):
    """查询录像/截图文件"""
    if not recorder:
        raise HTTPException(status_code=500, detail="录像模块未初始化")
    files = recorder.get_files(platform=platform, waybill=waybill, file_type=type)
    return {"files": files, "total": len(files)}


@router.get("/files/{filepath:path}")
async def get_file(filepath: str):
    """在线播放/下载文件"""
    # 安全检查：防止路径遍历
    if ".." in filepath:
        raise HTTPException(status_code=400, detail="非法路径")

    full_path = Path(filepath)
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    # 根据扩展名决定 Content-Type
    suffix = full_path.suffix.lower()
    media_types = {
        ".avi": "video/x-msvideo",
        ".mp4": "video/mp4",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }
    media_type = media_types.get(suffix, "application/octet-stream")

    return FileResponse(
        path=str(full_path),
        media_type=media_type,
        filename=full_path.name,
    )


# ─── 配置管理 ───

@router.get("/config")
async def get_config():
    """获取当前配置"""
    cm = ConfigManager()
    return cm.to_dict()


@router.put("/config")
async def update_config(data: dict):
    """更新配置"""
    global mjpeg_proxy
    cm = ConfigManager()
    
    # 先记录旧的摄像头配置
    old_cam = cm.config.camera
    
    # 更新配置
    cm.update(data)
    
    # 获取新的摄像头配置
    new_cam = cm.config.camera
    
    # 如果摄像头配置变化，重启摄像头
    if mjpeg_proxy and (
        old_cam.url != new_cam.url or
        old_cam.reconnect_interval_ms != new_cam.reconnect_interval_ms or
        old_cam.network_timeout_ms != new_cam.network_timeout_ms
    ):
        logger.info(f"摄像头配置已变更，重启连接")
        mjpeg_proxy.reload_url(
            url=new_cam.url,
            reconnect_interval_ms=new_cam.reconnect_interval_ms,
            network_timeout_ms=new_cam.network_timeout_ms,
        )
    
    # 重新加载语音配置
    if voice_speaker:
        voice_speaker.reload_config()
    # 重新加载 AI 配置
    if ai_analyzer:
        ai_analyzer.reload_config()
    logger.info("配置已更新")
    return {"ok": True, "message": "配置已更新"}


# ─── AI 日志 ───

@router.get("/ai/logs")
async def get_ai_logs():
    """获取 AI 分析日志"""
    if not ai_analyzer:
        return {"logs": []}
    return {"logs": ai_analyzer.logs}


# ─── WebSocket 实时状态推送 ───

@router.websocket("/ws/status")
async def ws_status(websocket: WebSocket):
    """WebSocket 实时状态推送"""
    await websocket.accept()
    async with _ws_lock:
        _ws_clients.append(websocket)
    try:
        while True:
            # 保持连接，接收客户端消息（心跳）
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=60)
            except asyncio.TimeoutError:
                # 超时发送心跳
                try:
                    status = await _get_current_status()
                    await websocket.send_json(status)
                except Exception:
                    break
            except WebSocketDisconnect:
                break
    finally:
        async with _ws_lock:
            if websocket in _ws_clients:
                _ws_clients.remove(websocket)


async def _get_current_status() -> dict:
    """获取当前状态字典"""
    cam_status = mjpeg_proxy.get_status() if mjpeg_proxy else {"connected": False, "url": ""}
    disk_info = recorder.get_disk_info() if recorder else {}
    return {
        "camera": cam_status,
        "recording": recorder.recording if recorder else False,
        "platform": recorder.current_platform if recorder else "",
        "waybill": recorder.current_waybill if recorder else "",
        "disk": disk_info,
        "ai_enabled": ai_analyzer.enabled if ai_analyzer else False,
    }


async def _broadcast_status():
    """向所有 WebSocket 客户端推送状态更新"""
    if not _ws_clients:
        return
    status = await _get_current_status()
    async with _ws_lock:
        for ws in _ws_clients[:]:
            try:
                await ws.send_json(status)
            except Exception:
                _ws_clients.remove(ws)
