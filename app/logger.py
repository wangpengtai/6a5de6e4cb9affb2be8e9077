# -*- coding: utf-8 -*-
"""日志工具模块 - 输出到文件和控制台"""

import logging
import os
from datetime import datetime
from pathlib import Path


class TagLogger:
    """带 TAG 的日志器，格式：[HH:mm:ss.fff] [LEVEL] [TAG] message"""

    def __init__(self, name: str = "app"):
        self._logger = logging.getLogger(name)
        self._tag = name.upper()

    def _format_msg(self, level: str, tag: str, msg: str) -> str:
        """格式化日志消息"""
        now = datetime.now().strftime("%H:%M:%S.") + f"{datetime.now().microsecond // 1000:03d}"
        return f"[{now}] [{level}] [{tag}] {msg}"

    def debug(self, msg: str, tag: str = None):
        """调试日志"""
        t = tag or self._tag
        self._logger.debug(self._format_msg("DEBUG", t, msg))

    def info(self, msg: str, tag: str = None):
        """信息日志"""
        t = tag or self._tag
        self._logger.info(self._format_msg("INFO", t, msg))

    def warning(self, msg: str, tag: str = None):
        """警告日志"""
        t = tag or self._tag
        self._logger.warning(self._format_msg("WARN", t, msg))

    def error(self, msg: str, tag: str = None):
        """错误日志"""
        t = tag or self._tag
        self._logger.error(self._format_msg("ERROR", t, msg))


# 全局日志目录
_LOG_DIR = Path(__file__).parent.parent / "logs"


class _DailyFileHandler(logging.FileHandler):
    """按日期切割的文件处理器"""

    def __init__(self, log_dir: Path, **kwargs):
        self._log_dir = log_dir
        self._current_date = ""
        # 先用临时文件名初始化
        super().__init__(log_dir / "temp.log", **kwargs)
        self._rotate_if_needed()

    def _rotate_if_needed(self):
        """检查日期变化，切换日志文件"""
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self._current_date:
            self._current_date = today
            new_path = self._log_dir / f"{today}.log"
            # 关闭旧流
            if self.stream:
                self.stream.close()
            self.stream = open(new_path, "a", encoding="utf-8")
            self.baseFilename = str(new_path)

    def emit(self, record):
        """写日志前检查日期"""
        self._rotate_if_needed()
        super().emit(record)


def setup_logger(name: str = "app") -> TagLogger:
    """初始化并获取 TagLogger 实例"""
    logger = logging.getLogger(name)

    # 避免重复添加 handler
    if logger.handlers:
        return TagLogger(name)

    logger.setLevel(logging.DEBUG)

    # 确保日志目录存在
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(console_handler)

    # 文件处理器（按日期切割）
    file_handler = _DailyFileHandler(_LOG_DIR)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(file_handler)

    return TagLogger(name)


# 模块级便捷函数
_default_logger: TagLogger = None


def get_logger(tag: str = None) -> TagLogger:
    """获取日志器，可指定 TAG"""
    global _default_logger
    if _default_logger is None:
        _default_logger = setup_logger("app")
    if tag:
        tl = TagLogger(tag)
        tl._logger = _default_logger._logger
        tl._tag = tag.upper()
        return tl
    return _default_logger
