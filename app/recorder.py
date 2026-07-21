# -*- coding: utf-8 -*-
"""录像管理模块 - 分段录像、多平台目录管理、磁盘空间检查"""

import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image
import io

from app.logger import get_logger
from app.config import ConfigManager

logger = get_logger("RECORDER")

# 支持的平台列表
PLATFORMS = ["douyin", "taobao", "jd", "other"]


class Recorder:
    """录像管理器：分段录像、运单绑定、磁盘空间管理"""

    def __init__(self):
        self._config = ConfigManager().config.storage
        self._recording = False
        self._writer: Optional[cv2.VideoWriter] = None
        self._current_file: Optional[str] = None
        self._current_platform: str = "other"
        self._current_waybill: str = ""
        self._segment_start: float = 0
        self._segment_index: int = 0
        self._record_dir = Path(self._config.record_dir)
        self._screenshot_dir = Path(self._config.screenshot_dir)

        # 确保目录存在
        self._ensure_dirs()

    def _ensure_dirs(self):
        """确保所有平台目录存在"""
        for d in [self._record_dir, self._screenshot_dir]:
            d.mkdir(parents=True, exist_ok=True)
        for platform in PLATFORMS:
            (self._record_dir / platform).mkdir(parents=True, exist_ok=True)
            (self._screenshot_dir / platform).mkdir(parents=True, exist_ok=True)

    @property
    def recording(self) -> bool:
        """是否正在录像"""
        return self._recording

    @property
    def current_platform(self) -> str:
        """当前绑定平台"""
        return self._current_platform

    @property
    def current_waybill(self) -> str:
        """当前绑定运单号"""
        return self._current_waybill

    def start_recording(self, fps: int = 15) -> bool:
        """开始录像"""
        if self._recording:
            logger.warning("已在录像中，忽略重复开始请求")
            return False

        # 检查磁盘空间
        if not self._check_disk_space():
            logger.error("磁盘空间不足，无法开始录像")
            return False

        self._segment_index = 0
        self._segment_start = time.time()
        filepath = self._generate_filepath()
        if not filepath:
            return False

        # 创建 VideoWriter（使用 MJPEG 编码，输出 AVI）
        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        self._writer = cv2.VideoWriter(filepath, fourcc, fps, (640, 480))
        if not self._writer.isOpened():
            logger.error("VideoWriter 创建失败")
            self._writer = None
            return False

        self._current_file = filepath
        self._recording = True
        logger.info(f"录像开始: {filepath}")
        return True

    def stop_recording(self) -> Optional[str]:
        """停止录像并归档，返回最终文件路径"""
        if not self._recording:
            return None

        self._recording = False
        filepath = self._current_file

        if self._writer:
            self._writer.release()
            self._writer = None

        # 归档到平台目录
        final_path = self._archive_file(filepath)
        logger.info(f"录像停止: {final_path}")

        # 清除绑定
        self._current_platform = "other"
        self._current_waybill = ""
        self._current_file = None

        return final_path

    def bind_waybill(self, platform: str, waybill: str):
        """绑定运单号和平台"""
        if platform not in PLATFORMS:
            platform = "other"
        self._current_platform = platform
        self._current_waybill = waybill
        logger.info(f"运单绑定: 平台={platform}, 运单号={waybill}")

    def write_frame(self, jpeg_data: bytes):
        """写入一帧到当前录像（从 JPEG bytes 解码为 BGR 后写入）"""
        if not self._recording or not self._writer:
            return

        # 检查是否需要分段
        elapsed = time.time() - self._segment_start
        if elapsed >= self._config.segment_seconds:
            self._rotate_segment()
            return

        try:
            # 从 JPEG bytes 解码
            nparr = np.frombuffer(jpeg_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if frame is not None:
                self._writer.write(frame)
        except Exception as e:
            logger.error(f"写帧失败: {e}")

    def save_screenshot(self, jpeg_data: bytes, platform: str = None) -> Optional[str]:
        """保存截图到对应平台目录"""
        plat = platform or self._current_platform
        if plat not in PLATFORMS:
            plat = "other"

        dir_path = self._screenshot_dir / plat
        dir_path.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        waybill_suffix = f"_{self._current_waybill}" if self._current_waybill else ""
        filename = f"{plat}{waybill_suffix}_{timestamp}.png"
        filepath = dir_path / filename

        try:
            img = Image.open(io.BytesIO(jpeg_data))
            img.save(str(filepath), "PNG")
            logger.info(f"截图已保存: {filepath}")
            return str(filepath)
        except Exception as e:
            logger.error(f"截图保存失败: {e}")
            return None

    def _generate_filepath(self) -> Optional[str]:
        """生成录像文件路径"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        waybill_suffix = f"_{self._current_waybill}" if self._current_waybill else ""

        # 录像期间先保存到临时目录
        temp_dir = self._record_dir / "_temp"
        temp_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{self._current_platform}{waybill_suffix}_{timestamp}_{self._segment_index}.avi"
        filepath = temp_dir / filename
        return str(filepath)

    def _rotate_segment(self):
        """切换到下一个录像分段"""
        # 关闭当前分段
        if self._writer:
            old_file = self._current_file
            self._writer.release()
            self._writer = None
            # 归档旧分段
            self._archive_file(old_file)

        # 开始新分段
        self._segment_index += 1
        self._segment_start = time.time()
        filepath = self._generate_filepath()
        if not filepath:
            self._recording = False
            return

        fps = ConfigManager().config.storage.fps
        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        self._writer = cv2.VideoWriter(filepath, fourcc, fps, (640, 480))
        if not self._writer.isOpened():
            logger.error("分段切换时 VideoWriter 创建失败")
            self._recording = False
            return
        self._current_file = filepath
        logger.info(f"录像分段切换: {filepath}")

    def _archive_file(self, filepath: Optional[str]) -> Optional[str]:
        """将录像文件归档到对应平台目录"""
        if not filepath or not Path(filepath).exists():
            return filepath

        src = Path(filepath)
        plat_dir = self._record_dir / self._current_platform
        plat_dir.mkdir(parents=True, exist_ok=True)
        dest = plat_dir / src.name

        try:
            shutil.move(str(src), str(dest))
            logger.info(f"录像归档: {dest}")
            return str(dest)
        except Exception as e:
            logger.error(f"录像归档失败: {e}")
            return filepath

    def _check_disk_space(self) -> bool:
        """检查磁盘剩余空间是否足够"""
        try:
            usage = shutil.disk_usage(self._record_dir.resolve())
            free_mb = usage.free // (1024 * 1024)
            if free_mb < self._config.min_free_space_mb:
                logger.warning(f"磁盘空间不足: 剩余 {free_mb}MB, 阈值 {self._config.min_free_space_mb}MB")
                # 尝试清理旧录像
                self._cleanup_old_files()
                # 再次检查
                usage = shutil.disk_usage(self._record_dir.resolve())
                free_mb = usage.free // (1024 * 1024)
                return free_mb >= self._config.min_free_space_mb
            return True
        except Exception as e:
            logger.error(f"磁盘空间检查失败: {e}")
            return True  # 检查失败时允许继续

    def _cleanup_old_files(self):
        """删除最早的录像文件以释放空间"""
        logger.info("开始清理旧录像文件...")
        all_files = []
        for platform in PLATFORMS:
            plat_dir = self._record_dir / platform
            if plat_dir.exists():
                for f in plat_dir.iterdir():
                    if f.is_file() and f.suffix == ".avi":
                        all_files.append(f)

        # 按修改时间排序，最早的在前
        all_files.sort(key=lambda f: f.stat().st_mtime)

        # 删除最早的文件直到空间足够
        usage = shutil.disk_usage(self._record_dir.resolve())
        free_mb = usage.free // (1024 * 1024)

        for f in all_files:
            if free_mb >= self._config.min_free_space_mb:
                break
            try:
                size_mb = f.stat().st_size // (1024 * 1024)
                f.unlink()
                free_mb += size_mb
                logger.info(f"已删除旧录像: {f} ({size_mb}MB)")
            except Exception as e:
                logger.error(f"删除旧录像失败: {f}, {e}")

    def get_files(self, platform: str = None, waybill: str = None, file_type: str = "record") -> list:
        """查询录像/截图文件列表"""
        result = []
        if file_type in ("record", "all"):
            result.extend(self._list_files(self._record_dir, ".avi", platform, waybill))
        if file_type in ("screenshot", "all"):
            result.extend(self._list_files(self._screenshot_dir, ".png", platform, waybill))
        # 按修改时间倒序
        result.sort(key=lambda x: x.get("mtime", ""), reverse=True)
        return result

    def _list_files(self, base_dir: Path, ext: str, platform: str = None, waybill: str = None) -> list:
        """列出指定目录下符合条件的文件"""
        result = []
        platforms = [platform] if platform and platform in PLATFORMS else PLATFORMS

        for plat in platforms:
            plat_dir = base_dir / plat
            if not plat_dir.exists():
                continue
            for f in plat_dir.iterdir():
                if not f.is_file() or f.suffix != ext:
                    continue
                name = f.stem
                # 运单号过滤
                if waybill and waybill not in name:
                    continue
                stat = f.stat()
                result.append({
                    "name": f.name,
                    "path": str(f).replace("\\", "/"),
                    "platform": plat,
                    "size": stat.st_size,
                    "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                })
        return result

    def get_disk_info(self) -> dict:
        """获取磁盘空间信息"""
        try:
            usage = shutil.disk_usage(self._record_dir.resolve())
            return {
                "total_mb": usage.total // (1024 * 1024),
                "used_mb": usage.used // (1024 * 1024),
                "free_mb": usage.free // (1024 * 1024),
            }
        except Exception as e:
            logger.error(f"获取磁盘信息失败: {e}")
            return {"total_mb": 0, "used_mb": 0, "free_mb": 0}
