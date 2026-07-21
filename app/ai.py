# -*- coding: utf-8 -*-
"""Ollama AI 分析模块 - 按间隔截取视频帧发送到 Ollama 进行分析"""

import asyncio
import base64
import time
from typing import Callable, Optional

import httpx

from app.logger import get_logger
from app.config import ConfigManager

logger = get_logger("AI")


class AiAnalyzer:
    """AI 分析器：定时截帧并请求 Ollama"""

    def __init__(self, get_frame_func: Callable[[], Optional[bytes]]):
        """
        Args:
            get_frame_func: 获取当前帧的回调函数，返回 JPEG bytes 或 None
        """
        self._get_frame = get_frame_func
        self._config = ConfigManager().config.ai
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._logs: list = []  # AI 分析日志
        self._max_logs = 100

    @property
    def enabled(self) -> bool:
        """是否启用"""
        return self._config.enabled

    @property
    def logs(self) -> list:
        """获取 AI 分析日志"""
        return self._logs.copy()

    def start(self):
        """启动 AI 分析（在已有事件循环中调用）"""
        if not self._config.enabled:
            logger.info("AI 分析未启用")
            return
        if self._running:
            return
        self._running = True
        self._task = asyncio.get_event_loop().create_task(self._analyze_loop())
        logger.info("AI 分析已启动")

    def stop(self):
        """停止 AI 分析"""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
        logger.info("AI 分析已停止")

    def reload_config(self):
        """重新加载配置"""
        old_enabled = self._config.enabled
        self._config = ConfigManager().config.ai
        if self._config.enabled and not old_enabled:
            self.start()
        elif not self._config.enabled and old_enabled:
            self.stop()

    async def _analyze_loop(self):
        """定时分析循环"""
        while self._running:
            try:
                frame = self._get_frame()
                if frame:
                    result = await self._request_ollama(frame)
                    if result:
                        self._add_log(result)
                await asyncio.sleep(self._config.interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"AI 分析循环异常: {e}")
                await asyncio.sleep(self._config.interval_seconds)

    async def _request_ollama(self, jpeg_data: bytes) -> Optional[str]:
        """发送帧到 Ollama 进行分析"""
        try:
            # 将 JPEG 编码为 base64
            img_b64 = base64.b64encode(jpeg_data).decode("utf-8")

            payload = {
                "model": self._config.model,
                "prompt": "请识别这张图片中的快递面单信息，提取以下内容：\n1. 运单号（快递单号）\n2. 快递公司名称\n3. 平台标识（如抖音、淘宝、京东等）\n4. 收件人信息\n5. 寄件人信息\n6. 商品信息\n\n请以结构化格式输出，例如：\n运单号：xxx\n快递公司：xxx\n平台：xxx",
                "images": [img_b64],
                "stream": False,
            }

            async with httpx.AsyncClient(timeout=self._config.timeout_seconds) as client:
                resp = await client.post(self._config.ollama_url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                result = data.get("response", "")
                if result:
                    logger.info(f"AI 分析结果: {result[:100]}...")
                return result
        except Exception as e:
            logger.error(f"Ollama 请求失败: {e}")
            return None

    def _add_log(self, result: str):
        """添加分析日志"""
        import datetime
        entry = {
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "result": result,
        }
        self._logs.append(entry)
        # 限制日志数量
        if len(self._logs) > self._max_logs:
            self._logs = self._logs[-self._max_logs:]
