# -*- coding: utf-8 -*-
"""配置管理模块 - 读取 config.json 并提供单例访问"""

import json
import threading
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class ServerConfig:
    """服务器配置"""
    host: str = "0.0.0.0"
    port: int = 8000


@dataclass
class CameraConfig:
    """摄像头配置"""
    url: str = "http://192.168.1.49:8089/videofeed"
    reconnect_interval_ms: int = 3000
    network_timeout_ms: int = 5000


@dataclass
class StorageConfig:
    """存储配置"""
    record_dir: str = "record"
    screenshot_dir: str = "snapshot"
    min_free_space_mb: int = 2048
    segment_seconds: int = 600
    fps: int = 15


@dataclass
class VoiceConfig:
    """语音配置"""
    enabled: bool = True
    volume: float = 1.0
    rate: int = 180


@dataclass
class AiConfig:
    """AI 分析配置"""
    enabled: bool = False
    ollama_url: str = "http://127.0.0.1:11434/api/generate"
    model: str = "llama3.2-vision"
    interval_seconds: int = 10
    timeout_seconds: int = 30


@dataclass
class AppConfig:
    """应用总配置"""
    server: ServerConfig = field(default_factory=ServerConfig)
    camera: CameraConfig = field(default_factory=CameraConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    ai: AiConfig = field(default_factory=AiConfig)


class ConfigManager:
    """配置管理器（单例），支持热更新"""

    _instance: Optional["ConfigManager"] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """单例模式"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, config_path: Optional[str] = None):
        if self._initialized:
            return
        self._initialized = True
        self._config_path = Path(config_path) if config_path else Path(__file__).parent.parent / "config.json"
        self._config = AppConfig()
        self._rw_lock = threading.RWLock() if hasattr(threading, "RWLock") else threading.Lock()
        self._load()

    def _load(self):
        """从 JSON 文件加载配置"""
        try:
            if self._config_path.exists():
                with open(self._config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._apply_data(data)
            else:
                # 配置文件不存在，使用默认值并创建文件
                self.save()
        except Exception as e:
            print(f"[ConfigManager] 加载配置失败: {e}，使用默认值")

    def _apply_data(self, data: dict):
        """将字典数据应用到配置对象"""
        if "server" in data:
            srv = data["server"]
            self._config.server = ServerConfig(
                host=srv.get("host", "0.0.0.0"),
                port=srv.get("port", 8000),
            )
        if "camera" in data:
            cam = data["camera"]
            self._config.camera = CameraConfig(
                url=cam.get("url", "http://192.168.1.49:8089/videofeed"),
                reconnect_interval_ms=cam.get("reconnect_interval_ms", 3000),
                network_timeout_ms=cam.get("network_timeout_ms", 5000),
            )
        if "storage" in data:
            sto = data["storage"]
            self._config.storage = StorageConfig(
                record_dir=sto.get("record_dir", "record"),
                screenshot_dir=sto.get("screenshot_dir", "snapshot"),
                min_free_space_mb=sto.get("min_free_space_mb", 2048),
                segment_seconds=sto.get("segment_seconds", 600),
                fps=sto.get("fps", 15),
            )
        if "voice" in data:
            voi = data["voice"]
            self._config.voice = VoiceConfig(
                enabled=voi.get("enabled", True),
                volume=voi.get("volume", 1.0),
                rate=voi.get("rate", 180),
            )
        if "ai" in data:
            ai = data["ai"]
            self._config.ai = AiConfig(
                enabled=ai.get("enabled", False),
                ollama_url=ai.get("ollama_url", "http://127.0.0.1:11434/api/generate"),
                model=ai.get("model", "llama3.2-vision"),
                interval_seconds=ai.get("interval_seconds", 10),
                timeout_seconds=ai.get("timeout_seconds", 30),
            )

    def reload(self):
        """热更新：重新从文件加载配置"""
        self._load()

    @property
    def config(self) -> AppConfig:
        """获取当前配置"""
        return self._config

    def update(self, data: dict):
        """用字典数据更新配置（部分更新）"""
        self._apply_data(data)
        self.save()

    def save(self):
        """将当前配置保存到 JSON 文件"""
        try:
            data = {
                "server": {
                    "host": self._config.server.host,
                    "port": self._config.server.port,
                },
                "camera": {
                    "url": self._config.camera.url,
                    "reconnect_interval_ms": self._config.camera.reconnect_interval_ms,
                    "network_timeout_ms": self._config.camera.network_timeout_ms,
                },
                "storage": {
                    "record_dir": self._config.storage.record_dir,
                    "screenshot_dir": self._config.storage.screenshot_dir,
                    "min_free_space_mb": self._config.storage.min_free_space_mb,
                    "segment_seconds": self._config.storage.segment_seconds,
                    "fps": self._config.storage.fps,
                },
                "voice": {
                    "enabled": self._config.voice.enabled,
                    "volume": self._config.voice.volume,
                    "rate": self._config.voice.rate,
                },
                "ai": {
                    "enabled": self._config.ai.enabled,
                    "ollama_url": self._config.ai.ollama_url,
                    "model": self._config.ai.model,
                    "interval_seconds": self._config.ai.interval_seconds,
                    "timeout_seconds": self._config.ai.timeout_seconds,
                },
            }
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[ConfigManager] 保存配置失败: {e}")

    def to_dict(self) -> dict:
        """将配置转为字典"""
        return {
            "server": {
                "host": self._config.server.host,
                "port": self._config.server.port,
            },
            "camera": {
                "url": self._config.camera.url,
                "reconnect_interval_ms": self._config.camera.reconnect_interval_ms,
                "network_timeout_ms": self._config.camera.network_timeout_ms,
            },
            "storage": {
                "record_dir": self._config.storage.record_dir,
                "screenshot_dir": self._config.storage.screenshot_dir,
                "min_free_space_mb": self._config.storage.min_free_space_mb,
                "segment_seconds": self._config.storage.segment_seconds,
                "fps": self._config.storage.fps,
            },
            "voice": {
                "enabled": self._config.voice.enabled,
                "volume": self._config.voice.volume,
                "rate": self._config.voice.rate,
            },
            "ai": {
                "enabled": self._config.ai.enabled,
                "ollama_url": self._config.ai.ollama_url,
                "model": self._config.ai.model,
                "interval_seconds": self._config.ai.interval_seconds,
                "timeout_seconds": self._config.ai.timeout_seconds,
            },
        }
