"""
playlist_manager.py - 播放列表管理
负责播放列表的加载、保存、管理
"""

import json
import logging
import tempfile
import os
from pathlib import Path
from typing import List, Optional, Tuple

from utils import PlatformCompat

logger = logging.getLogger(__name__)


class PlaylistManager:
    """播放列表管理器类"""
    
    def __init__(self, app_name: str = "飞羽播放器", dev_dir: Optional[Path] = None):
        """
        初始化播放列表管理器
        
        Args:
            app_name: 应用名称，用于创建存储目录
            dev_dir: 开发环境目录，如果为 None 则使用当前文件所在目录
        """
        if dev_dir is None:
            dev_dir = Path(__file__).resolve().parent
        
        self._playlist_root = PlatformCompat.get_storage_dir(app_name, dev_dir)
        self._playlist_store = self._playlist_root / "playlist.m3u"
        self._state_store = self._playlist_root / "playlist_state.json"
        
        # 确保目录存在
        try:
            self._playlist_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.error("Failed to create storage directory %s: %s", self._playlist_root, exc)
        
        # 播放列表数据
        self.files: List[str] = []
        self.current_index: int = -1
        self.remove_behavior: str = "next"  # "next" | "stop"
        
        # 加载现有数据
        self._load_playlist_from_disk()
    
    def _to_store_path(self, filepath: str) -> str:
        """将文件路径转换为存储路径（相对路径）"""
        path = Path(filepath)
        try:
            rel = path.resolve().relative_to(self._playlist_root)
            return rel.as_posix()
        except ValueError:
            return str(path.resolve())
    
    def _resolve_store_path(self, stored: str) -> Path:
        """将存储路径解析为绝对路径"""
        path = Path(stored)
        if not path.is_absolute():
            path = (self._playlist_root / path).resolve()
        else:
            path = path.resolve()
        return path
    
    def _atomic_write_text(self, path: Path, content: str):
        """原子写入文本文件"""
        tmp_path = None
        try:
            fd, tmp_name = tempfile.mkstemp(
                prefix=f"{path.stem}.", suffix=".tmp", dir=str(path.parent)
            )
            tmp_path = Path(tmp_name)
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as tmpf:
                tmpf.write(content)
            os.replace(tmp_path, path)
        except (OSError, UnicodeError) as exc:
            logger.error("Atomic write failed for %s: %s", path, exc)
            if tmp_path and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    logger.debug("Failed to remove temp file: %s", tmp_path)
    
    def add_files(self, file_paths: List[str]) -> int:
        """
        添加文件到播放列表
        
        Args:
            file_paths: 文件路径列表
            
        Returns:
            添加的文件数量
        """
        added_count = 0
        for file_path in file_paths:
            if file_path not in self.files:
                self.files.append(file_path)
                added_count += 1
        
        if added_count > 0:
            self.save_to_disk()
        
        return added_count
    
    def remove_file(self, index: int) -> bool:
        """
        从播放列表中移除文件
        
        Args:
            index: 要移除的文件索引
            
        Returns:
            是否成功移除
        """
        if 0 <= index < len(self.files):
            self.files.pop(index)
            
            # 调整当前索引
            if index == self.current_index:
                if self.remove_behavior == "next" and self.files:
                    self.current_index = -1  # 将在外部处理下一首播放
                else:
                    self.current_index = -1
            elif index < self.current_index:
                self.current_index -= 1
            
            self.save_to_disk()
            return True
        return False
    
    def move_file_up(self, index: int) -> bool:
        """
        将文件上移
        
        Args:
            index: 要移动的文件索引
            
        Returns:
            是否成功移动
        """
        if index <= 0 or index >= len(self.files):
            return False
        
        # 交换位置
        self.files[index - 1], self.files[index] = (
            self.files[index],
            self.files[index - 1],
        )
        
        # 调整当前索引
        if self.current_index == index:
            self.current_index = index - 1
        elif self.current_index == index - 1:
            self.current_index = index
        
        self.save_to_disk()
        return True
    
    def move_file_down(self, index: int) -> bool:
        """
        将文件下移
        
        Args:
            index: 要移动的文件索引
            
        Returns:
            是否成功移动
        """
        if index < 0 or index >= len(self.files) - 1:
            return False
        
        # 交换位置
        self.files[index], self.files[index + 1] = (
            self.files[index + 1],
            self.files[index],
        )
        
        # 调整当前索引
        if self.current_index == index:
            self.current_index = index + 1
        elif self.current_index == index + 1:
            self.current_index = index
        
        self.save_to_disk()
        return True
    
    def clear(self):
        """清空播放列表"""
        self.files.clear()
        self.current_index = -1
        self.save_to_disk()
    
    def get_file(self, index: int) -> Optional[str]:
        """获取指定索引的文件路径"""
        if 0 <= index < len(self.files):
            return self.files[index]
        return None
    
    def get_current_file(self) -> Optional[str]:
        """获取当前播放的文件路径"""
        return self.get_file(self.current_index)
    
    def set_current_index(self, index: int) -> bool:
        """
        设置当前播放索引
        
        Args:
            index: 新的当前索引
            
        Returns:
            是否成功设置
        """
        if 0 <= index < len(self.files) or index == -1:
            self.current_index = index
            self.save_to_disk()
            return True
        return False
    
    def next_index(self) -> Optional[int]:
        """获取下一首的索引，如果已经是最后一首则返回 None"""
        if self.current_index < len(self.files) - 1:
            return self.current_index + 1
        return None
    
    def prev_index(self) -> Optional[int]:
        """获取上一首的索引，如果已经是第一首则返回 None"""
        if self.current_index > 0:
            return self.current_index - 1
        return None
    
    def has_files(self) -> bool:
        """检查播放列表是否有文件"""
        return len(self.files) > 0
    
    def count(self) -> int:
        """获取播放列表中的文件数量"""
        return len(self.files)
    
    def save_to_disk(self):
        """保存播放列表到磁盘"""
        try:
            lines = ["#EXTM3U", f"#CURRENT:{self.current_index}"]
            for f in self.files:
                lines.append(self._to_store_path(f))
            self._atomic_write_text(self._playlist_store, "\n".join(lines) + "\n")
        except (OSError, UnicodeError, ValueError) as exc:
            logger.error("Saving playlist failed: %s", exc)
    
    def _load_playlist_from_disk(self):
        """从磁盘加载播放列表"""
        if not self._playlist_store.exists():
            return
        
        try:
            lines = self._playlist_store.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            logger.error("Loading playlist failed: %s", exc)
            return
        
        files: List[str] = []
        saved_idx = -1
        
        for raw in lines:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#CURRENT:"):
                try:
                    saved_idx = int(line.split(":", 1)[1].strip())
                except ValueError:
                    saved_idx = -1
                continue
            if line.startswith("#"):
                continue
            files.append(line)
        
        self.files = []
        for f in files:
            if not isinstance(f, str):
                continue
            resolved = self._resolve_store_path(f)
            if resolved.exists():
                fp = str(resolved)
                self.files.append(fp)
        
        if 0 <= saved_idx < len(self.files):
            self.current_index = saved_idx
    
    def save_state(self, state_data: dict):
        """
        保存应用状态
        
        Args:
            state_data: 状态数据字典
        """
        try:
            self._atomic_write_text(
                self._state_store,
                json.dumps(state_data, ensure_ascii=False, indent=2) + "\n",
            )
        except (OSError, ValueError, TypeError) as exc:
            logger.error("Saving app state failed: %s", exc)
    
    def load_state(self) -> dict:
        """
        加载应用状态
        
        Returns:
            状态数据字典
        """
        if not self._state_store.exists():
            return {}
        
        try:
            state = json.loads(self._state_store.read_text(encoding="utf-8"))
            return state
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            logger.error("Loading app state failed: %s", exc)
            return {}