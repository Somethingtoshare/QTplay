"""
utils.py - 工具函数和平台兼容性
"""

import logging
import os
import sys
from pathlib import Path

if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
logger = logging.getLogger(__name__)


class PlatformCompat:
    @staticmethod
    def supports_window_shadow() -> bool:
        return not sys.platform.startswith("win")

    @staticmethod
    def is_frozen_app() -> bool:
        return bool(getattr(sys, "frozen", False))

    @staticmethod
    def get_storage_dir(app_name: str, dev_dir: Path) -> Path:
        if not PlatformCompat.is_frozen_app():
            return dev_dir
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / app_name
        return Path.home() / f".{app_name}"


def get_resource_path(relative_path: str) -> str:
    """获取资源绝对路径，兼容 PyInstaller 打包
    
    在开发环境中，返回相对于当前工作目录的路径。
    在 PyInstaller 打包后（--onefile 模式），返回解压到临时目录的路径。
    
    Args:
        relative_path: 相对路径，如 "Assets/VT323/VT323-Regular.ttf"
    
    Returns:
        资源的绝对路径字符串
    """
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller 打包后的临时目录
        return os.path.join(sys._MEIPASS, relative_path)
    # 开发环境，使用当前目录
    return os.path.join(os.path.abspath("."), relative_path)