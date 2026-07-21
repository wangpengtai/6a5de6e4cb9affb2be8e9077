# -*- coding: utf-8 -*-
"""语音播报模块 - 使用 pyttsx3 在独立线程中播报"""

import queue
import threading
from typing import Optional

from app.logger import get_logger
from app.config import ConfigManager

logger = get_logger("VOICE")


class VoiceSpeaker:
    """语音播报器：独立线程运行，不阻塞主线程"""

    def __init__(self):
        self._config = ConfigManager().config.voice
        self._queue: queue.Queue = queue.Queue()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._engine = None
        self._lock = threading.Lock()

    def start(self):
        """启动语音播报线程"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("语音播报线程已启动")

    def stop(self):
        """停止语音播报线程"""
        self._running = False
        # 放入空消息唤醒线程
        self._queue.put(None)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None
        logger.info("语音播报线程已停止")

    def speak(self, text: str):
        """加入播报队列"""
        if not self._config.enabled:
            return
        if not text:
            return
        self._queue.put(text)

    def _run_loop(self):
        """播报线程主循环"""
        try:
            import pyttsx3
            self._engine = pyttsx3.init()
            self._engine.setProperty("volume", self._config.volume)
            self._engine.setProperty("rate", self._config.rate)
        except Exception as e:
            logger.error(f"pyttsx3 初始化失败: {e}，语音播报不可用")
            self._running = False
            return

        while self._running:
            try:
                text = self._queue.get(timeout=1)
                if text is None:
                    continue
                self._do_speak(text)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"语音播报异常: {e}")

        # 清理引擎
        try:
            if self._engine:
                self._engine.stop()
        except Exception:
            pass

    def _do_speak(self, text: str):
        """执行单次播报"""
        try:
            with self._lock:
                if self._engine:
                    self._engine.say(text)
                    self._engine.runAndWait()
            logger.info(f"语音播报: {text}")
        except Exception as e:
            logger.error(f"播报失败: {e}")

    def reload_config(self):
        """重新加载配置"""
        self._config = ConfigManager().config.voice
        if self._engine:
            try:
                self._engine.setProperty("volume", self._config.volume)
                self._engine.setProperty("rate", self._config.rate)
            except Exception as e:
                logger.error(f"更新语音配置失败: {e}")
