# -*- coding: utf-8 -*-
"""MJPEG 视频流转发模块 - 从 IP Webcam 拉取 MJPEG 流并转发"""

import io
import queue
import threading
import time
from typing import Callable, Optional

import httpx
from PIL import Image

from app.logger import get_logger

logger = get_logger("VIDEO")


class MjpegProxy:
    """MJPEG 视频流代理：从 IP Webcam 拉取 MJPEG 流，提供帧获取和流转发"""

    # JPEG 起始和结束标记
    JPEG_START = b"\xff\xd8"
    JPEG_END = b"\xff\xd9"

    def __init__(
        self,
        url: str,
        reconnect_interval_ms: int = 3000,
        network_timeout_ms: int = 5000,
        on_status_change: Optional[Callable[[str], None]] = None,
        on_disconnect: Optional[Callable[[], None]] = None,
        on_reconnect: Optional[Callable[[], None]] = None,
    ):
        self._url = url
        self._reconnect_interval = reconnect_interval_ms / 1000.0
        self._network_timeout = network_timeout_ms / 1000.0
        self._on_status_change = on_status_change
        self._on_disconnect = on_disconnect
        self._on_reconnect = on_reconnect

        # 线程安全队列，只保留最新一帧
        self._frame_queue: queue.Queue = queue.Queue(maxsize=1)
        self._latest_frame: Optional[bytes] = None
        self._frame_lock = threading.Lock()

        # 控制标志
        self._running = False
        self._connected = False
        self._was_connected = False  # 是否曾经连接成功过（用于区分首次连接 vs 重连）
        self._thread: Optional[threading.Thread] = None

    @property
    def connected(self) -> bool:
        """是否已连接"""
        return self._connected

    def _set_connected(self, value: bool):
        """设置连接状态并触发回调"""
        old = self._connected
        self._connected = value
        if old != value:
            if self._on_status_change:
                try:
                    self._on_status_change("connected" if value else "disconnected")
                except Exception:
                    pass
            if not value and self._on_disconnect:
                try:
                    self._on_disconnect()
                except Exception:
                    pass
            if value and not old and self._was_connected and self._on_reconnect:
                try:
                    self._on_reconnect()
                except Exception:
                    pass
            if value and not old:
                self._was_connected = True

    def start(self):
        """启动视频流拉取"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._pull_loop, daemon=True)
        self._thread.start()
        logger.info("MJPEG 拉流线程已启动")

    def stop(self):
        """停止视频流拉取"""
        self._running = False
        self._set_connected(False)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None
        logger.info("MJPEG 拉流线程已停止")

    def reload_url(self, url: str, reconnect_interval_ms: int = None, network_timeout_ms: int = None):
        """重新加载 URL 并重启连接"""
        if self._running:
            self.stop()
        self._url = url
        if reconnect_interval_ms is not None:
            self._reconnect_interval = reconnect_interval_ms / 1000.0
        if network_timeout_ms is not None:
            self._network_timeout = network_timeout_ms / 1000.0
        self.start()

    def get_latest_frame(self) -> Optional[bytes]:
        """获取最新一帧 JPEG 数据"""
        with self._frame_lock:
            return self._latest_frame

    def get_status(self) -> dict:
        """获取连接状态"""
        return {
            "connected": self._connected,
            "url": self._url,
        }

    async def stream_generator(self):
        """异步生成器：产出 MJPEG 流边界数据，用于 FastAPI StreamingResponse"""
        boundary = "--frameboundary"
        while self._running:
            frame = self.get_latest_frame()
            if frame:
                yield (
                    f"{boundary}\r\n"
                    f"Content-Type: image/jpeg\r\n"
                    f"Content-Length: {len(frame)}\r\n"
                    f"\r\n"
                ).encode("utf-8") + frame + b"\r\n"
            else:
                # 无帧时短暂等待
                await _async_sleep(0.05)

    def _pull_loop(self):
        """后台线程：持续拉取 MJPEG 流"""
        while self._running:
            try:
                self._pull_stream()
            except Exception as e:
                logger.error(f"拉流异常: {e}")
                self._set_connected(False)
            if self._running:
                logger.info(f"{self._reconnect_interval}秒后重连...")
                time.sleep(self._reconnect_interval)

    def _pull_stream(self):
        """使用 httpx 同步客户端拉取 MJPEG 流"""
        logger.info(f"正在连接: {self._url}")
        with httpx.Client(timeout=httpx.Timeout(self._network_timeout)) as client:
            with client.stream("GET", self._url) as resp:
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")
                self._set_connected(True)
                logger.info(f"连接成功, Content-Type: {content_type}")

                if "multipart/x-mixed-replace" in content_type:
                    # 标准 MJPEG 流：multipart/x-mixed-replace 格式
                    self._parse_multipart(resp)
                else:
                    # 裸 JPEG 流：FFD8...FFD9
                    self._parse_raw_jpeg(resp)

    def _parse_multipart(self, resp):
        """解析 multipart/x-mixed-replace 格式的 MJPEG 流"""
        buffer = b""
        # 提取 boundary
        ct = resp.headers.get("content-type", "")
        boundary = ""
        for part in ct.split(";"):
            part = part.strip()
            if part.startswith("boundary="):
                boundary = part[len("boundary="):].strip('"')
                break
        if not boundary:
            boundary = "--jpgboundary"

        boundary_bytes = boundary.encode("utf-8")

        for chunk in resp.iter_bytes(chunk_size=65536):
            if not self._running:
                break
            buffer += chunk

            # 按 boundary 分割
            while boundary_bytes in buffer:
                idx = buffer.find(boundary_bytes)
                part = buffer[:idx]
                buffer = buffer[idx + len(boundary_bytes):]

                # 在 part 中查找 JPEG 数据
                jpeg_data = self._extract_jpeg(part)
                if jpeg_data:
                    self._on_frame(jpeg_data)

    def _parse_raw_jpeg(self, resp):
        """解析裸 JPEG 流（FFD8...FFD9）"""
        buffer = b""
        for chunk in resp.iter_bytes(chunk_size=65536):
            if not self._running:
                break
            buffer += chunk

            # 查找所有完整的 JPEG 帧
            while True:
                start = buffer.find(self.JPEG_START)
                if start == -1:
                    buffer = buffer[-4:]  # 保留尾部避免截断起始标记
                    break
                end = buffer.find(self.JPEG_END, start + 2)
                if end == -1:
                    # 不完整帧，等待更多数据
                    buffer = buffer[start:]
                    break
                # 提取完整 JPEG 帧（含结束标记的2字节）
                jpeg_data = buffer[start:end + 2]
                buffer = buffer[end + 2:]
                self._on_frame(jpeg_data)

    def _extract_jpeg(self, data: bytes) -> Optional[bytes]:
        """从 multipart 部分中提取 JPEG 数据"""
        start = data.find(self.JPEG_START)
        if start == -1:
            return None
        end = data.find(self.JPEG_END, start + 2)
        if end == -1:
            return None
        return data[start:end + 2]

    def _on_frame(self, jpeg_data: bytes):
        """收到一帧时的处理"""
        with self._frame_lock:
            self._latest_frame = jpeg_data
        # 非阻塞方式放入队列（丢弃旧帧）
        try:
            self._frame_queue.get_nowait()
        except queue.Empty:
            pass
        try:
            self._frame_queue.put_nowait(jpeg_data)
        except queue.Full:
            pass

    def save_screenshot(self, filepath: str) -> bool:
        """将当前帧保存为 PNG 截图"""
        frame = self.get_latest_frame()
        if not frame:
            logger.warning("无可用帧，截图失败")
            return False
        try:
            img = Image.open(io.BytesIO(frame))
            img.save(filepath, "PNG")
            logger.info(f"截图已保存: {filepath}")
            return True
        except Exception as e:
            logger.error(f"截图保存失败: {e}")
            return False


# 异步 sleep 辅助
import asyncio


async def _async_sleep(seconds: float):
    await asyncio.sleep(seconds)
