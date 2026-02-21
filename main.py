"""
main.py - QT-Player 一个Qt播放器 (Refactored v3.0 - Vinyl & Sprites)
依赖: PyQt6, mutagen
作者：6666
"""

import json
import logging
import math
import os
import random
import sys
import tempfile
import time
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import (
    QEvent,
    QEasingCurve,
    QPropertyAnimation,
    QVariantAnimation,
    QSize,
    Qt,
    QTimer,
    QUrl,
    pyqtProperty,  # type: ignore
)
from PyQt6.QtGui import (
    QAction,
    QAbstractTextDocumentLayout,
    QColor,
    QFont,
    QFontDatabase,
    QLinearGradient,
    QIcon,
    QImage,
    QPainter,
    QPainterPath,
    QPixmap,
    QTextDocument,
)
from PyQt6.QtMultimedia import QAudioOutput, QMediaMetaData, QMediaPlayer
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStackedLayout,
    QStackedWidget,
    QStyle,
    QVBoxLayout,
    QWidget,
)

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
        relative_path: 相对路径，如 "Assets/digital_7/digital-7.ttf"
    
    Returns:
        资源的绝对路径字符串
    """
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller 打包后的临时目录
        return os.path.join(sys._MEIPASS, relative_path)
    # 开发环境，使用当前目录
    return os.path.join(os.path.abspath("."), relative_path)

# 尝试导入 mutagen 依赖
if TYPE_CHECKING:
    from mutagen import File
    from mutagen.id3 import APIC, ID3
    from mutagen.mp3 import MP3
    from mutagen.mp4 import MP4

try:
    import mutagen  # type: ignore
    from mutagen import File  # type: ignore
    from mutagen.id3 import APIC, ID3  # type: ignore
    from mutagen.mp3 import MP3  # type: ignore
    from mutagen.mp4 import MP4  # type: ignore

    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False
    MP4 = None  # type: ignore
    MP3 = None  # type: ignore
    ID3 = None  # type: ignore
    APIC = None  # type: ignore
    File = None  # type: ignore
    logger.warning("mutagen is not installed; metadata and embedded lyric parsing are limited.")

if MUTAGEN_AVAILABLE:
    MUTAGEN_ERRORS = (mutagen.MutagenError, OSError, ValueError, TypeError)  # type: ignore
else:
    MUTAGEN_ERRORS = (OSError, ValueError, TypeError)





class AudioMetadata:
    """Parse metadata (title/artist/format/cover) from audio files."""
    _CACHE: dict[tuple[str, int], "AudioMetadata"] = {}
    _CACHE_LIMIT = 256

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.title: str = ""
        self.artist: str = ""
        self.format_str: str = ""
        self.cover_data: bytes | None = None
        self.lyrics_text: str | None = None
        self._parse()

    @classmethod
    def from_file(cls, filepath: str) -> "AudioMetadata":
        path = Path(filepath)
        key_path = str(path.resolve()) if path.exists() else str(path.absolute())
        try:
            mtime_ns = path.stat().st_mtime_ns
        except OSError:
            mtime_ns = -1
        cache_key = (key_path, mtime_ns)
        cached = cls._CACHE.get(cache_key)
        if cached:
            return cached
        meta = cls(filepath)
        cls._CACHE[cache_key] = meta
        if len(cls._CACHE) > cls._CACHE_LIMIT:
            cls._CACHE.pop(next(iter(cls._CACHE)))
        return meta

    def _parse(self):
        ext = Path(self.filepath).suffix.lower()
        if ext == ".m4a":
            self._parse_m4a()
        elif ext == ".mp3":
            self._parse_mp3()

        if not self.lyrics_text:
            self._parse_generic()
        if not self.title:
            stem = Path(self.filepath).stem
            if " - " in stem:
                parts = stem.split(" - ", 1)
                self.artist = parts[0].strip()
                self.title = parts[1].strip()
            else:
                self.title = stem

    def _parse_m4a(self):
        if not MUTAGEN_AVAILABLE:
            return
        assert MP4 is not None
        try:
            tags = MP4(self.filepath)
            self.title = str(tags.get("\xa9nam", [""])[0])  # type: ignore
            self.artist = str(tags.get("\xa9ART", [""])[0])  # type: ignore
            info = tags.info
            self.format_str = f"格式: M4A  {int(getattr(info, 'sample_rate', 0) / 1000)}kHz  {int(getattr(info, 'bitrate', 0) / 1000)}K"
            covers = tags.get("covr", [])
            if covers:
                self.cover_data = bytes(covers[0])
            lyr = tags.get("\xa9lyr", [])
            if lyr:
                self.lyrics_text = str(lyr[0])
        except MUTAGEN_ERRORS as exc:
            logger.debug("M4A metadata parse failed for %s: %s", self.filepath, exc)

    def _parse_mp3(self):
        if not MUTAGEN_AVAILABLE:
            return
        assert MP3 is not None
        assert ID3 is not None
        assert APIC is not None
        try:
            audio = MP3(self.filepath)
            info = audio.info
            self.format_str = f"格式: MP3  {int(getattr(info, 'sample_rate', 0) / 1000)}kHz  {int(getattr(info, 'bitrate', 0) / 1000)}K"
            tags = ID3(self.filepath)
            title_tag = tags.get("TIT2")
            if title_tag:
                self.title = str(title_tag)
            artist_tag = tags.get("TPE1")
            if artist_tag:
                self.artist = str(artist_tag)
            for key, tag in tags.items():
                if isinstance(tag, APIC):
                    self.cover_data = tag.data  # type: ignore
                elif "USLT" in key or "LYRICS" in key.upper():
                    if hasattr(tag, "text") and tag.text:
                        self.lyrics_text = (
                            "\n".join(tag.text)
                            if isinstance(tag.text, list)
                            else str(tag.text)
                        )
        except MUTAGEN_ERRORS as exc:
            logger.debug("MP3 metadata parse failed for %s: %s", self.filepath, exc)

    def _parse_generic(self):
        if not MUTAGEN_AVAILABLE:
            return
        assert File is not None
        try:
            audio = File(self.filepath)
            if not audio:
                return
            for key in list(audio.keys()):
                if any(k in str(key).lower() for k in ["lyr", "lrc", "lyrics"]):
                    val = audio[key]
                    text = (
                        "\n".join(map(str, val))
                        if isinstance(val, (list, tuple))
                        else str(val)
                    )
                    if "[" in text:
                        self.lyrics_text = text
                        break
        except MUTAGEN_ERRORS as exc:
            logger.debug("Generic lyric parse failed for %s: %s", self.filepath, exc)

    @property
    def display_name(self) -> str:
        if self.artist and self.title:
            return f"{self.artist} - {self.title}"
        return self.title or Path(self.filepath).stem


# 歌词解析器

class LrcParser:
    def __init__(self, filepath_or_text: str, is_text: bool = False):
        self.lyrics: list[tuple[int, str]] = []
        if is_text:
            self._parse_content(filepath_or_text)
        else:
            self._parse_file(filepath_or_text)

    def _parse_file(self, filepath: str):
        if not os.path.exists(filepath):
            return
        content = ""
        for enc in ["utf-8-sig", "utf-8", "gb18030", "utf-16"]:
            try:
                with open(filepath, "r", encoding=enc) as f:
                    content = f.read()
                break
            except (UnicodeDecodeError, OSError):
                continue
        if content:
            self._parse_content(content)

    def _parse_content(self, content: str):
        import re

        time_regex = re.compile(r"\[(\d+):(\d+(?:[\.\:]\d+)?)\]")
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            matches = time_regex.findall(line)
            if not matches:
                continue
            text = line[line.rfind("]") + 1 :].strip()
            for m, s in matches:
                try:
                    self.lyrics.append((int(m) * 60000 + int(float(s) * 1000), text))
                except ValueError:
                    continue
        self.lyrics.sort()
        if not self.lyrics and content.strip():
            self.lyrics.append((0, content.strip()))

    def get_current_index(self, current_ms: int) -> int:
        if not self.lyrics:
            return -1
        idx = -1
        for i, (ms, _) in enumerate(self.lyrics):
            if ms <= current_ms:
                idx = i
            else:
                break
        return idx


# 视觉组件：黑胶唱片、按钮、滑块

class VinylCover(QWidget):
    """Vinyl cover widget with rotation animation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(240, 240)
        self._pixmap = None
        self._angle = 0

        # 旋转动画
        self.anim = QPropertyAnimation(self, b"rotation")
        self.anim.setDuration(12000)  # 12 秒一圈
        self.anim.setStartValue(0)
        self.anim.setEndValue(360)
        self.anim.setLoopCount(-1)  # 无限循环
        self.anim.setEasingCurve(QEasingCurve.Type.Linear)

        # 阴影
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 150))
        shadow.setOffset(0, 5)
        self.setGraphicsEffect(shadow)

    def set_cover(self, pixmap: QPixmap | None):
        """Set cover image and crop it into a circle."""
        size = 240
        if pixmap and not pixmap.isNull():
            # Scale & Crop
            scaled = pixmap.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )

            # Create Circular Pixmap
            dest = QPixmap(size, size)
            dest.fill(Qt.GlobalColor.transparent)

            painter = QPainter(dest)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            # Setup path
            path = QPainterPath()
            path.addEllipse(0, 0, size, size)
            painter.setClipPath(path)

            # Draw image
            painter.drawPixmap(0, 0, scaled)

            # Draw center hole (Vinyl look)
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_DestinationOut
            )
            painter.setBrush(QColor(0, 0, 0, 255))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(size // 2 - 15, size // 2 - 15, 30, 30)  # 30px hole

            # Add some vinyl texture/shine (optional, keeping simple for now)

            painter.end()
            self._pixmap = dest
        else:
            # Default placeholder (Gray Vinyl)
            dest = QPixmap(size, size)
            dest.fill(Qt.GlobalColor.transparent)
            painter = QPainter(dest)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QColor(30, 30, 30))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(0, 0, size, size)
            # Hole
            painter.setBrush(
                QColor(0, 0, 0)
            )  # Actually transparent in widget but black here
            painter.drawEllipse(size // 2 - 15, size // 2 - 15, 30, 30)
            painter.end()
            self._pixmap = dest
        self.update()

    def start_anim(self):
        if self.anim.state() != QPropertyAnimation.State.Running:
            self.anim.start()

    def pause_anim(self):
        self.anim.pause()

    def stop_anim(self):
        self.anim.stop()
        self._angle = 0
        self.update()

    def get_rotation(self):
        return self._angle

    def set_rotation(self, angle):
        self._angle = angle
        self.update()

    rotation = pyqtProperty(float, get_rotation, set_rotation)  # type: ignore

    def paintEvent(self, event):
        if not self._pixmap:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Translate to center, rotate, translate back
        cx, cy = self.width() / 2, self.height() / 2
        painter.translate(cx, cy)
        painter.rotate(self._angle)
        painter.translate(-cx, -cy)

        offset_x = (self.width() - self._pixmap.width()) / 2
        offset_y = (self.height() - self._pixmap.height()) / 2
        painter.drawPixmap(int(offset_x), int(offset_y), self._pixmap)


class ClickableSlider(QSlider):
    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            val = (
                self.minimum()
                + (self.maximum() - self.minimum()) * event.pos().x() / self.width()
            )
            event.accept()
            self.sliderMoved.emit(int(val))


class DotMatrixLabel(QLabel):
    """RichText label with explicit antialias render pass for soft VFD-like glow."""

    def paintEvent(self, event):
        _ = event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        doc = QTextDocument(self)
        doc.setDocumentMargin(0)
        doc.setDefaultFont(self.font())
        doc.setHtml(self.text())
        doc.setTextWidth(float(self.width()))
        y = max(0.0, (self.height() - doc.size().height()) * 0.5)
        painter.save()
        painter.translate(0.0, y)
        ctx = QAbstractTextDocumentLayout.PaintContext()
        doc.documentLayout().draw(painter, ctx)
        painter.restore()


class LyricDisplay(QWidget):
    """Custom lyric display widget with smooth scrolling and gradient mask.
    
    Features:
    - Fixed height for exactly 5 lines of lyrics
    - QPropertyAnimation-driven smooth scrolling
    - Current line highlighted with accent color (18px)
    - Non-current lines semi-transparent (14px)
    - Top/bottom gradient mask for fade effect
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # 固定高度：5行 × 28px = 140px
        self.setFixedHeight(140)
        
        # 歌词数据
        self._lyrics: list[tuple[int, str]] = []
        self._current_index: int = -1
        self._scroll_offset: float = 0.0
        self._accent_color: QColor = QColor("#A7F3D0")
        self._bg_color: QColor = QColor("#1E293B")
        
        # 行高配置
        self._line_height: int = 28
        self._visible_lines: int = 5
        
        # 滚动动画
        self._scroll_anim = QPropertyAnimation(self, b"scroll_offset", self)
        self._scroll_anim.setDuration(260)
        self._scroll_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        
        # 设置无焦点策略
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        
    def set_accent_color(self, color: QColor):
        """Set the accent color for current line highlighting."""
        if color and color.isValid():
            self._accent_color = QColor(color)
            self.update()
    
    def set_bg_color(self, color: QColor):
        """Set the background color for gradient mask."""
        if color and color.isValid():
            self._bg_color = QColor(color)
            self.update()
    
    def get_scroll_offset(self) -> float:
        return self._scroll_offset
    
    def set_scroll_offset(self, value: float):
        self._scroll_offset = value
        self.update()
    
    scroll_offset = pyqtProperty(float, get_scroll_offset, set_scroll_offset)  # type: ignore
    
    def set_lyrics(self, lyrics: list[tuple[int, str]]):
        """Set the lyrics data and reset state."""
        self._lyrics = lyrics
        self._current_index = -1
        self._scroll_offset = 0.0
        self._scroll_anim.stop()
        self.update()
    
    def set_current_index(self, index: int, animate: bool = True):
        """Set the current lyric index and scroll to center it."""
        if index == self._current_index:
            return
        if not self._lyrics:
            return
        
        # 限制索引范围
        index = max(0, min(index, len(self._lyrics) - 1))
        self._current_index = index
        
        if animate:
            # 计算目标滚动偏移，使当前行居中
            # 目标：当前行应该在组件的垂直中心
            target_offset = index * self._line_height
            self._animate_scroll_to(target_offset)
        else:
            self._scroll_offset = index * self._line_height
            self.update()
    
    def _animate_scroll_to(self, target: float):
        """Animate scroll to target offset."""
        self._scroll_anim.stop()
        self._scroll_anim.setStartValue(self._scroll_offset)
        self._scroll_anim.setEndValue(target)
        self._scroll_anim.start()
    
    def clear_lyrics(self):
        """Clear all lyrics."""
        self._lyrics = []
        self._current_index = -1
        self._scroll_offset = 0.0
        self._scroll_anim.stop()
        self.update()
    
    def set_status(self, text: str):
        """Display a status message (no lyrics)."""
        self._lyrics = [(0, text)]
        self._current_index = 0
        self._scroll_offset = 0.0
        self._scroll_anim.stop()
        self.update()
    
    def paintEvent(self, event):
        """Paint lyrics with brightness gradient based on distance from current line."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        
        # 填充背景（透明）
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        
        if not self._lyrics:
            return
        
        # 计算绘制参数
        width = self.width()
        height = self.height()
        center_y = height / 2
        
        # 计算第一行歌词的 Y 坐标
        # 滚动偏移为 0 时，第一行在中心位置
        first_line_y = center_y - self._scroll_offset
        
        # 绘制每一行歌词
        for i, (_, text) in enumerate(self._lyrics):
            line_y = first_line_y + i * self._line_height
            
            # 跳过完全不可见的行
            if line_y < -self._line_height or line_y > height + self._line_height:
                continue
            
            # 计算距离当前行的距离
            diff = abs(i - self._current_index)
            
            # 根据距离设置字体亮度渐变
            if diff == 0:
                # 当前行：最亮，白色，大字号，粗体
                font_size = 16
                color = QColor(255, 255, 255, 255)  # #FFFFFF
                font_weight = QFont.Weight.Bold
            elif diff == 1:
                # 上下第一行：次亮
                font_size = 14
                color = QColor(255, 255, 255, 120)
                font_weight = QFont.Weight.Normal
            elif diff == 2:
                # 上下第二行：很暗
                font_size = 14
                color = QColor(255, 255, 255, 50)
                font_weight = QFont.Weight.Normal
            else:
                # 距离更远的：几乎看不见（完全透明）
                font_size = 14
                color = QColor(255, 255, 255, 0)
                font_weight = QFont.Weight.Normal
            
            font = QFont("Microsoft YaHei", font_size, font_weight)
            painter.setFont(font)
            painter.setPen(color)
            
            # 居中绘制文本
            fm = painter.fontMetrics()
            text_width = fm.horizontalAdvance(text)
            text_x = (width - text_width) / 2
            text_y = line_y + fm.ascent() - fm.height() / 2
            
            painter.drawText(int(text_x), int(text_y), text)
        
        # 不再绘制渐变遮罩，保持纯透明背景
    
    def _draw_gradient_mask(self, painter: QPainter):
        """Draw gradient mask with pure fade effect.
        
        关键：使用完全相同的背景色，只改变 Alpha 通道。
        - 顶部/底部边缘：完全不透明（alpha=255），遮盖歌词
        - 中间区域：完全透明（alpha=0），显示歌词
        """
        # 获取背景色，确保完全不透明
        bg = QColor(self._bg_color)
        bg.setAlpha(255)  # 强制设置 alpha 为 255，确保完全不透明
        
        # 创建渐变
        gradient = QLinearGradient(0, 0, 0, self.height())
        
        # 顶部消隐：0% -> 20% 从背景色过渡到透明
        gradient.setColorAt(0.0, bg)  # 完全不透明的背景色
        gradient.setColorAt(0.2, QColor(bg.red(), bg.green(), bg.blue(), 0))  # 完全透明
        
        # 底部消隐：80% -> 100% 从透明过渡到背景色
        gradient.setColorAt(0.8, QColor(bg.red(), bg.green(), bg.blue(), 0))  # 完全透明
        gradient.setColorAt(1.0, bg)  # 完全不透明的背景色
        
        painter.fillRect(self.rect(), gradient)


class SpectrumWidget(QWidget):
    """Dot-matrix spectrum with fast rise, damped fall and peak hold."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(120, 48)
        self._bar_count = 12
        self._levels = [0.0] * self._bar_count
        self._peaks = [0.0] * self._bar_count
        self._peak_hold_until = [0.0] * self._bar_count
        self._active = False
        self._phase = 0.0
        self._breath_phase = 0.0
        self._rng = random.Random()
        self._cell = 3
        self._step = 4
        self._bottom_pad = 2
        self._accent = QColor("#A7F3D0")
        self._timer = QTimer(self)
        self._timer.setInterval(33)  # ~30 FPS
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def set_accent_color(self, color: QColor):
        if color and color.isValid():
            self._accent = QColor(color)
            self.update()

    def set_active(self, active: bool):
        self._active = bool(active)
        if not self._active:
            self._phase = 0.0

    def _max_rows(self) -> int:
        return max(4, (self.height() - 4) // self._step)

    def _tick(self):
        now = time.monotonic()
        self._phase += 0.23 if self._active else 0.06
        self._breath_phase += 0.09
        max_rows = float(self._max_rows())
        for i in range(self._bar_count):
            if self._active:
                wave = 0.5 + 0.5 * math.sin(self._phase + i * 0.58)
                jitter = self._rng.uniform(0.0, 0.45)
                target = min(1.0, wave * 0.75 + jitter * 0.55)
                # Fast rise
                if target > self._levels[i]:
                    self._levels[i] += (target - self._levels[i]) * 0.95
                # Damped fall while playing
                else:
                    self._levels[i] = self._levels[i] * 0.86 + target * 0.14
            else:
                # Wake-up standby remains at 1 lit cell; decay one-step-at-a-time feel.
                rows = self._levels[i] * max_rows
                if rows > 1.0:
                    rows = max(1.0, rows - 0.18)
                else:
                    rows = 1.0
                self._levels[i] = rows / max_rows

            level_rows = max(1.0, self._levels[i] * max_rows)
            if level_rows >= self._peaks[i]:
                self._peaks[i] = level_rows
                self._peak_hold_until[i] = now + 0.5
            elif now > self._peak_hold_until[i]:
                self._peaks[i] = max(0.0, self._peaks[i] - 0.22)
        self.update()

    def paintEvent(self, event):
        _ = event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setPen(Qt.PenStyle.NoPen)

        max_rows = self._max_rows()
        count = self._bar_count
        bar_w = self._cell
        usable_w = max(1, self.width() - 4)
        gap = max(1, (usable_w - count * bar_w) // max(1, (count - 1)))
        total_w = count * bar_w + (count - 1) * gap
        start_x = (self.width() - total_w) // 2
        base_y = self.height() - self._bottom_pad - self._cell

        for i in range(count):
            x = start_x + i * (bar_w + gap)
            level = int(round(self._levels[i] * max_rows))
            peak = int(round(self._peaks[i]))

            # Draw full dark column in standby/active as the base grid.
            for row in range(max_rows):
                y = base_y - row * self._step
                dark = QColor(self._accent)
                dark.setAlpha(38)
                painter.fillRect(x, y, self._cell, self._cell, dark)

            lit_rows = max(1, min(max_rows, level))
            for row in range(lit_rows):
                y = base_y - row * self._step
                c = QColor(self._accent)
                if not self._active and row == 0:
                    # Standby breathing light (0.6 -> 1.0 alpha)
                    breathing = 0.8 + 0.2 * math.sin(self._breath_phase + i * 0.35)
                    c.setAlpha(int(255 * max(0.6, min(1.0, breathing))))
                else:
                    alpha = 135 + int((row / max(1, max_rows)) * 120)
                    c.setAlpha(min(250, alpha))
                painter.fillRect(x, y, self._cell, self._cell, c)
            if self._active and peak > lit_rows:
                py = base_y - min(max_rows - 1, peak) * self._step
                peak_c = QColor(self._accent)
                peak_c.setAlpha(250)
                painter.fillRect(x, py, self._cell, self._cell, peak_c)


# 主题管理器

class ThemeManager:
    THEMES = {
        "自适应": {"mode": "cover"},
        "深海": {
            "window_grad": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0F172A, stop:1 #1E293B)",
            "panel_left": "#1E293B",
            "text_p": "#F8FAFC",
            "text_s": "#CBD5E1",
            "accent": "#38BDF8",
            "btn_hover": "rgba(56, 189, 248, 0.22)",
            "border": "rgba(56, 189, 248, 0.35)",
            "shadow": "#38BDF8",
        },
        "黑曜": {
            "window_grad": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #000000, stop:1 #1A1A1A)",
            "panel_left": "#1A1A1A",
            "text_p": "#FFFFFF",
            "text_s": "#E4E4E7",
            "accent": "#E50914",
            "btn_hover": "rgba(229, 9, 20, 0.22)",
            "border": "rgba(229, 9, 20, 0.35)",
            "shadow": "#E50914",
        },
        "翡翠": {
            "window_grad": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #064E3B, stop:1 #065F46)",
            "panel_left": "#065F46",
            "text_p": "#ECFDF5",
            "text_s": "#A7F3D0",
            "accent": "#34D399",
            "btn_hover": "rgba(52, 211, 153, 0.24)",
            "border": "rgba(52, 211, 153, 0.35)",
            "shadow": "#34D399",
        },
        "赛博": {
            "window_grad": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #020617, stop:1 #1E1B4B)",
            "panel_left": "#1E1B4B",
            "text_p": "#FAE8FF",
            "text_s": "#E9D5FF",
            "accent": "#F472B6",
            "btn_hover": "rgba(244, 114, 182, 0.24)",
            "border": "rgba(244, 114, 182, 0.35)",
            "shadow": "#F472B6",
        },
        "侘寂": {
            "window_grad": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #27272A, stop:1 #3F3F46)",
            "panel_left": "#3F3F46",
            "text_p": "#F4F4F5",
            "text_s": "#D4D4D8",
            "accent": "#A1A1AA",
            "btn_hover": "rgba(161, 161, 170, 0.24)",
            "border": "rgba(161, 161, 170, 0.35)",
            "shadow": "#A1A1AA",
        },
        "暗金": {
            "window_grad": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1C1917, stop:1 #292524)",
            "panel_left": "#292524",
            "text_p": "#FAFAF9",
            "text_s": "#E7E5E4",
            "accent": "#D97706",
            "btn_hover": "rgba(217, 119, 6, 0.24)",
            "border": "rgba(217, 119, 6, 0.35)",
            "shadow": "#D97706",
        },
        "幽灵": {
            "window_grad": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #09090B, stop:1 #18181B)",
            "panel_left": "#18181B",
            "text_p": "#E4E4E7",
            "text_s": "#A1A1AA",
            "accent": "#6366F1",
            "btn_hover": "rgba(99, 102, 241, 0.24)",
            "border": "rgba(99, 102, 241, 0.35)",
            "shadow": "#6366F1",
        },
        "波尔多": {
            "window_grad": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #450A0A, stop:1 #7F1D1D)",
            "panel_left": "#7F1D1D",
            "text_p": "#FEF2F2",
            "text_s": "#FECACA",
            "accent": "#F87171",
            "btn_hover": "rgba(248, 113, 113, 0.24)",
            "border": "rgba(248, 113, 113, 0.35)",
            "shadow": "#F87171",
        },
        "极光": {
            "window_grad": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #022C22, stop:1 #064E3B)",
            "panel_left": "#064E3B",
            "text_p": "#F0FDFA",
            "text_s": "#CCFBF1",
            "accent": "#A7F3D0",
            "btn_hover": "rgba(167, 243, 208, 0.24)",
            "border": "rgba(167, 243, 208, 0.35)",
            "shadow": "#A7F3D0",
        },
        "宇宙": {
            "window_grad": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #171717, stop:1 #262626)",
            "panel_left": "#262626",
            "text_p": "#F5F3FF",
            "text_s": "#DDD6FE",
            "accent": "#8B5CF6",
            "btn_hover": "rgba(139, 92, 246, 0.24)",
            "border": "rgba(139, 92, 246, 0.35)",
            "shadow": "#8B5CF6",
        },
    }

    @staticmethod
    def _rgba(color: QColor, alpha: float) -> str:
        a = max(0.0, min(1.0, alpha))
        return f"rgba({color.red()}, {color.green()}, {color.blue()}, {a:.2f})"

    @staticmethod
    def _contrast_text(color: QColor) -> str:
        luminance = 0.2126 * color.red() + 0.7152 * color.green() + 0.0722 * color.blue()
        return "#0B1220" if luminance > 150 else "#F8FAFC"

    @staticmethod
    def build_adaptive_palette(seed_color: QColor | None) -> dict[str, str]:
        seed = QColor(seed_color) if seed_color and seed_color.isValid() else QColor("#0B1220")
        hsv = seed.toHsv()
        h, s, v, a = hsv.getHsv()
        if h < 0:
            h = 120
        s = max(51, min(102, s))  # 20% - 40%
        v = max(38, min(64, v))   # 15% - 25%
        bg_start = QColor.fromHsv(h, s, v, a)
        bg_end = QColor("#000000")
        panel = QColor.fromHsv(h, max(40, min(90, s + 8)), max(20, v - 6), a)
        accent = QColor.fromHsv((h + 180) % 360, 180, 228, a)
        muted = accent.lighter(120)

        bg_grad = (
            "qlineargradient(x1:0, y1:0, x2:1, y2:1, "
            f"stop:0 {bg_start.name()}, stop:1 {bg_end.name()})"
        )
        return {
            "window_grad": bg_grad,
            "bg": bg_grad,
            "panel": panel.name(),
            "accent": accent.name(),
            "text": "#F8FAFC",
            "muted": muted.name(),
            "border": ThemeManager._rgba(accent, 0.38),
            "btn_hover": ThemeManager._rgba(accent, 0.24),
            "shadow": accent.name(),
            "hover_text": ThemeManager._contrast_text(accent),
        }

    @staticmethod
    def resolve(theme_name: str, palette_override: dict[str, str] | None = None) -> dict[str, str]:
        if theme_name == "自适应" and palette_override:
            return palette_override
        if theme_name == "自适应":
            return ThemeManager.build_adaptive_palette(QColor("#0B1220"))
        raw = ThemeManager.THEMES.get(theme_name, ThemeManager.THEMES["极光"])
        panel = raw.get("panel", raw.get("panel_left", "#1E293B"))
        accent_color = QColor(raw.get("accent", "#A7F3D0"))
        return {
            "window_grad": raw.get("window_grad", panel),
            "bg": raw.get("bg", raw.get("window_grad", panel)),
            "panel": panel,
            "accent": accent_color.name(),
            "text": raw.get("text", raw.get("text_p", "#F0FDFA")),
            "muted": raw.get("muted", raw.get("text_s", "#CCFBF1")),
            "border": raw.get("border", "rgba(167, 243, 208, 0.35)"),
            "btn_hover": raw.get("btn_hover", "rgba(167, 243, 208, 0.24)"),
            "shadow": raw.get("shadow", accent_color.name()),
            "hover_text": ThemeManager._contrast_text(accent_color),
        }

    @staticmethod
    def get_style(theme_name, palette_override: dict[str, str] | None = None):
        t = ThemeManager.resolve(theme_name, palette_override)
        # 预处理颜色用于样式表
        accent_color = QColor(t["accent"])
        accent_darker = accent_color.darker(140)  # 用于阴影
        
        # 为按钮准备拟物化颜色
        # 亮色边缘和深色阴影
        accent_light = accent_color.lighter(120)
        accent_dark = accent_color.darker(130)
        
        return f"""
            QMainWindow {{ background: transparent; }}
            QWidget#CentralWidget {{
                background: {t["bg"]};
                border: 1px solid {t["border"]};
                border-radius: 16px;
            }}
            QWidget#LeftPanel, QWidget#RightPanel {{
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 12px;
            }}
            QWidget#LeftPanel {{ background-color: {t["panel"]}; }}
            QWidget#RightPanel {{ background-color: {t["panel"]}; }}

            /* 顶部按钮 - 极简风格，仅悬停时高亮 */
            QPushButton#TopButton {{
                background-color: transparent;
                border: none;
                border-radius: 6px;
                color: {t["text"]};
                font-weight: bold;
                padding: 3px;
            }}
            QPushButton#TopButton:hover {{
                background-color: {ThemeManager._rgba(accent_color, 0.12)};
                color: {t["text"]};
            }}
            QPushButton#TopButton:pressed {{
                background-color: {ThemeManager._rgba(accent_color, 0.18)};
                padding-top: 4px; padding-left: 4px;
            }}

            /* 控制按钮 - 拟物化风格 */
            QPushButton#ControlButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {ThemeManager._rgba(accent_light, 0.30)},
                    stop:1 {ThemeManager._rgba(accent_color, 0.20)});
                border: 1px solid rgba(161, 161, 170, 0.1);
                border-radius: 9px;
                background-clip: padding-box;
                color: {t["text_s"] if "text_s" in t else t["text"]};
                font-weight: bold;
                padding: 0px;
                margin: 0px;
            }}
            QPushButton#ControlButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {ThemeManager._rgba(accent_light, 0.40)},
                    stop:1 {ThemeManager._rgba(accent_color, 0.30)});
                border: 1px solid rgba(161, 161, 170, 0.15);
                color: {t["text_p"] if "text_p" in t else t["text"]};
            }}
            QPushButton#ControlButton:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {ThemeManager._rgba(accent_color, 0.15)},
                    stop:1 {ThemeManager._rgba(accent_light, 0.25)});
                border: 1px solid rgba(161, 161, 170, 0.1);
                padding-top: 1px; padding-left: 1px;
            }}

            /* 播放按钮 - 视觉重心加强 */
            QPushButton#PlayButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {ThemeManager._rgba(accent_light, 0.35)},
                    stop:1 {ThemeManager._rgba(accent_color, 0.25)});
                border: 1px solid rgba(161, 161, 170, 0.1);
                border-radius: 10px;
                background-clip: padding-box;
                color: {t["text_s"] if "text_s" in t else t["text"]};
                font-weight: bold;
                padding: 0px;
                margin: 0px;
            }}
            QPushButton#PlayButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {ThemeManager._rgba(accent_light, 0.45)},
                    stop:1 {ThemeManager._rgba(accent_color, 0.35)});
                border: 1px solid rgba(161, 161, 170, 0.15);
                color: {t["text_p"] if "text_p" in t else t["text"]};
            }}
            QPushButton#PlayButton:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {ThemeManager._rgba(accent_color, 0.20)},
                    stop:1 {ThemeManager._rgba(accent_light, 0.30)});
                border: 1px solid rgba(161, 161, 170, 0.1);
                padding-top: 2px; padding-left: 2px;
            }}

            /* 全局按钮 - 其他按钮的默认样式 */
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {t["accent"]}, stop:1 {t["btn_hover"]});
                border: 2px solid {t["accent"]};
                border-radius: 8px;
                color: {t["text"]};
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {QColor(t["accent"]).lighter(115).name()}, stop:1 {QColor(t["btn_hover"]).lighter(120).name()});
                border: 2px solid {QColor(t["accent"]).lighter(130).name()};
                color: {t["hover_text"]};
            }}
            QPushButton:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {QColor(t["accent"]).darker(110).name()}, stop:1 {QColor(t["accent"]).darker(130).name()});
                border: 2px solid {t["text"]};
                padding-top: 2px; padding-left: 2px;
            }}


            QLabel {{ color: {t["text"]}; font-family: 'Segoe UI', 'Microsoft YaHei'; }}
            QWidget#TelemetryPanel {{
                background: transparent;
                border-radius: 0px;
            }}
            QWidget#DotInfoContainer {{
                background: transparent;
            }}
            QLabel#InfoLineTop, QLabel#InfoLineBottom {{
                font-size: 12px;
                font-weight: 500;
                background: transparent;
                padding: 0px;
                margin: 0px;
            }}

            QListWidget {{
                background: transparent; color: {t["text"]}; border: none; outline: none;
            }}
            QListWidget#PlaylistList {{
                background: transparent;
                border: none;
                outline: none;
            }}
            QListWidget#PlaylistList::item {{
                padding: 10px;
                border: none;
                margin: 0px;
                border-radius: 0px;
                color: {t["muted"]};
                font-size: 15px;
            }}
            QListWidget#PlaylistList::item:selected {{
                background-color: {t["btn_hover"]};
                color: {t["text"]};
                border-left: 3px solid {t["accent"]};
                border-radius: 0px;
            }}
            QListWidget#PlaylistList::item:hover {{
                background-color: {t["btn_hover"]};
                color: {t["text"]};
            }}
            QListWidget::item {{
                padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.05); color: {t["muted"]};
            }}
            QListWidget::item:selected {{
                background-color: {t["btn_hover"]}; color: {t["accent"]}; border-left: 3px solid {t["accent"]};
            }}
            QListWidget::item:hover {{ background-color: {t["btn_hover"]}; }}
            QScrollBar:vertical {{
                width: 8px;
                background: rgba(0, 0, 0, 0.2);
                border-radius: 4px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical {{
                background: {t["accent"]};
                min-height: 30px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {QColor(t["accent"]).lighter(120).name()};
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {{
                background: transparent;
            }}

            QSlider {{ min-height: 24px; }}
            QSlider::groove:horizontal {{
                height: 4px; background: rgba(255,255,255,0.2); border-radius: 2px; margin: 10px 0;
            }}
            QSlider::sub-page:horizontal {{
                background: {t["accent"]}; border-radius: 2px; margin: 10px 0;
            }}
            QSlider::handle:horizontal {{
                background: {t["accent"]}; width: 18px; height: 18px; margin: -7px 0;
                border-radius: 9px; border: 2px solid #fff;
            }}

            QMenu {{ background: {t["bg"]}; border: 1px solid {t["border"]}; color: {t["text"]}; }}
            QMenu::item:selected {{ background: {t["accent"]}; color: {t["hover_text"]}; }}
        """


# 主窗口

class MainPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self._init_done = False
        self.current_accent_color = QColor("#A7F3D0")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Mobile-like default viewport (close to iPhone SE 375:667 ratio).
        self.resize(388, 690)
        self.setWindowTitle("QTPlay v1.0")

        # 初始化 UI
        self._init_ui()

        # 播放核心
        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)

        self._playlist_root = PlatformCompat.get_storage_dir(
            "TTPlayer", Path(__file__).resolve().parent
        )
        try:
            self._playlist_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.error("Failed to create storage directory %s: %s", self._playlist_root, exc)
        self._playlist_store = self._playlist_root / "playlist.m3u"
        self._state_store = self._playlist_root / "playlist_state.json"
        self._remove_behavior = "next"  # "next" | "stop"
        self._lyrics_follow_enabled = True
        self._lyrics_lock_line = False
        self._lyrics_offset_ms = 0
        self._resume_position_ms = 0

        self.current_theme = "自适应"
        self._default_seed_color = QColor("#0B1220")
        self._active_theme_palette = ThemeManager.build_adaptive_palette(self._default_seed_color)
        self._bg_anim = QVariantAnimation(self)
        self._bg_anim.setDuration(280)
        self._bg_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._bg_anim.valueChanged.connect(self._on_bg_anim_value_changed)
        self._bg_from_color = QColor(self._default_seed_color)
        self._bg_to_color = QColor(self._default_seed_color)
        self.apply_theme(self.current_theme)

        # 定时器
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._on_timer)

        self._connect_signals()

        # 状态
        self._drag_pos = None
        self.playlist_files = []  # List[str]
        self._view_mode = 0  # 0: Main, 1: Playlist
        self._current_index = -1
        self._base_window_width = 388
        self._pending_restore_view_mode: int | None = None
        self._last_lyric_index = -2  # 初始化歌词索引
        self._load_app_state()
        self._load_playlist_from_disk()
        self._restore_last_track()
        QTimer.singleShot(0, self._apply_restored_view_mode)
        self._init_done = True

    def _create_button(self, icon_source, tooltip):
        btn = QPushButton()
        btn.setObjectName("ControlButton")
        setattr(btn, "_icon_source", icon_source)
        btn.setIconSize(QSize(32, 32))
        self._apply_button_icon(btn)
        btn.setFixedSize(48, 48)
        btn.setToolTip(tooltip)
        return btn

    def _build_dot_matrix_font(self) -> QFont:
        font_family = None
        font_source = None
        # 使用 get_resource_path 兼容开发环境和 PyInstaller 打包
        font_candidates = [
            "Assets/digital_7/digital-7.ttf",
            "Assets/digital_7/digital-7 (mono).ttf",
            "Assets/digital_7/digital-7 (mono italic).ttf",
            "Assets/digital_7/digital-7 (italic).ttf",
        ]
        for rel_path in font_candidates:
            fp = Path(get_resource_path(rel_path))
            try:
                if not fp.exists():
                    continue
                font_id = QFontDatabase.addApplicationFont(str(fp))
                if font_id < 0:
                    continue
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    font_family = families[0]
                    font_source = fp
                    break
            except OSError:
                continue
        font = QFont(font_family or "Consolas", 11)
        font.setKerning(False)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.6)
        self._dot_font_family = font.family()
        if font_source is not None:
            logger.info("Dot matrix font loaded: %s (%s)", self._dot_font_family, font_source)
        else:
            logger.warning("Dot matrix font fallback in use: %s", self._dot_font_family)
        return font

    def _fit_icon_canvas(self, pixmap: QPixmap, target: QSize) -> QPixmap:
        if pixmap.isNull() or not target.isValid():
            return pixmap
        src = pixmap
        dpr = src.devicePixelRatio()
        if dpr and abs(dpr - 1.0) > 1e-6:
            # Normalize HiDPI pixmap to logical pixels before further processing.
            logical = src.deviceIndependentSize().toSize()
            if logical.isValid():
                src = src.scaled(
                    logical,
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                src.setDevicePixelRatio(1.0)
        src = src.scaled(
            target,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        canvas = QPixmap(target)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        x = (target.width() - src.width()) // 2
        y = (target.height() - src.height()) // 2
        painter.drawPixmap(x, y, src)
        painter.end()
        return canvas

    def _apply_button_icon(self, btn: QPushButton):
        icon_source = getattr(btn, "_icon_source", None)
        if icon_source is None:
            return
        size = btn.iconSize()
        if isinstance(icon_source, QStyle.StandardPixmap):
            style = self.style()
            if not style:
                return
            raw_icon = style.standardIcon(icon_source)
            fitted = self._fit_icon_canvas(raw_icon.pixmap(size), size)
            btn.setIcon(QIcon(fitted))
            return
        if isinstance(icon_source, QPixmap):
            src = self._fit_icon_canvas(icon_source, size)
            btn.setIcon(QIcon(src))
            return
        btn.setIcon(QIcon())
        logger.warning("Unknown icon_source type for button: %s", type(icon_source))

    def apply_button_style(self, button: QPushButton, accent_color: QColor):
        if not accent_color.isValid():
            accent_color = QColor("#A7F3D0")
        base = QColor(accent_color)
        top = QColor(base).lighter(118)
        bottom = QColor(base).darker(115)
        edge = QColor(base).darker(130)
        glow = QColor(base)
        glow.setAlpha(120)
        button.setFixedSize(48, 48)
        button.setIconSize(QSize(24, 24))
        button.setStyleSheet(
            f"""
            QPushButton {{
                margin: 0px;
                padding: 0px;
                min-width: 48px;
                max-width: 48px;
                min-height: 48px;
                max-height: 48px;
                border-radius: 6px;
                border: 2px solid {edge.name()};
                background-color: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 {top.name()},
                    stop:1 {bottom.name()}
                );
            }}
            QPushButton:hover {{
                border: 2px solid {base.name()};
                background-color: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 {QColor(base).lighter(130).name()},
                    stop:1 {QColor(base).darker(105).name()}
                );
            }}
            QPushButton:pressed {{
                border: 2px solid {QColor(base).darker(145).name()};
                background-color: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 {QColor(base).darker(110).name()},
                    stop:1 {QColor(base).darker(140).name()}
                );
                padding-top: 1px;
                padding-left: 1px;
            }}
            """
        )
        setattr(button, "_hover_accent_color", glow)

    def _set_button_glow(self, button: QPushButton, enabled: bool):
        if not enabled:
            button.setGraphicsEffect(None)
            return
        accent = getattr(button, "_hover_accent_color", QColor("#A7F3D0"))
        glow_color = QColor(accent)
        glow_color.setAlpha(115)
        glow = QGraphicsDropShadowEffect(button)
        glow.setBlurRadius(16)
        glow.setOffset(0, 0)
        glow.setColor(glow_color)
        button.setGraphicsEffect(glow)

    def _refresh_media_control_button_styles(self):
        if not all(
            hasattr(self, n) for n in ("btn_prev", "btn_play", "btn_next", "btn_pause")
        ):
            return
        for btn in (self.btn_prev, self.btn_play, self.btn_next, self.btn_pause):
            if not getattr(btn, "_control_hover_filter_bound", False):
                btn.installEventFilter(self)
                setattr(btn, "_control_hover_filter_bound", True)

    def _refresh_button_icons(self):
        for btn in self.findChildren(QPushButton):
            if hasattr(btn, "_icon_source"):
                self._apply_button_icon(btn)

    def _init_ui(self):
        self.central_widget = QWidget()
        self.central_widget.setObjectName("CentralWidget")
        self.setCentralWidget(self.central_widget)

        # Shadow (Windows layered window + drop shadow effect can trigger
        # UpdateLayeredWindowIndirect parameter errors during resize/animation).
        if PlatformCompat.supports_window_shadow():
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(18)
            shadow.setColor(QColor(0, 0, 0, 180))
            shadow.setOffset(0, 0)
            self.central_widget.setGraphicsEffect(shadow)

        # 使用像素固定布局：三个固定高度的区域
        root = QVBoxLayout(self.central_widget)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(0)  # 无间距，完全像素控制

        # 第一区：主题行（0-40像素）
        self.top_frame = QFrame()
        self.top_frame.setObjectName("TopFrame")
        self.top_frame.setFixedHeight(40)  # 固定40像素高度
        top_layout = QVBoxLayout(self.top_frame)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)
        
        # 窗口控制行 - 统一顶部标题栏布局
        win_ctrl_layout = QHBoxLayout()
        win_ctrl_layout.setContentsMargins(0, 0, 0, 0)
        win_ctrl_layout.setSpacing(8)
        
        # 主题按钮
        self.btn_theme = QPushButton("主题")
        self.btn_theme.setObjectName("TopButton")
        self.btn_theme.setFixedSize(40, 28)
        theme_menu = QMenu(self)
        for t in ThemeManager.THEMES.keys():
            action = QAction(t, self)
            action.triggered.connect(lambda _, n=t: self.apply_theme(n))
            theme_menu.addAction(action)
        self.btn_theme.setMenu(theme_menu)
        
        # 最小化按钮
        self.btn_min = QPushButton("-")
        self.btn_min.setObjectName("TopButton")
        self.btn_min.setFixedSize(28, 28)
        self.btn_min.clicked.connect(self.showMinimized)
        
        # 关闭按钮
        self.btn_close = QPushButton("x")
        self.btn_close.setObjectName("TopButton")
        self.btn_close.setFixedSize(28, 28)
        self.btn_close.clicked.connect(self.close)
        
        # 标题文字 - TTplayer（主界面）或播放列表（播放列表界面）
        self.lbl_title = QLabel("TTplayer")
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #F8FAFC;")
        
        # 布局：主题按钮 + 弹性空间 + 标题文字 + 弹性空间 + 最小化按钮 + 关闭按钮
        win_ctrl_layout.addWidget(self.btn_theme)
        win_ctrl_layout.addStretch()
        win_ctrl_layout.addWidget(self.lbl_title)
        win_ctrl_layout.addStretch()
        win_ctrl_layout.addWidget(self.btn_min)
        win_ctrl_layout.addWidget(self.btn_close)
        
        top_layout.addLayout(win_ctrl_layout)
        root.addWidget(self.top_frame)

        # 第二区：内容区（40-580像素，540像素高度）
        self.content_frame = QFrame()
        self.content_frame.setObjectName("ContentFrame")
        self.content_frame.setFixedHeight(540)  # 固定540像素高度
        content_layout = QVBoxLayout(self.content_frame)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # 内容区将使用QStackedWidget来切换主界面和播放列表内容
        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("ContentStack")
        
        # 主界面内容
        self.main_content = QWidget()
        main_content_layout = QVBoxLayout(self.main_content)
        main_content_layout.setContentsMargins(0, 0, 0, 0)
        main_content_layout.setSpacing(4)
        
        # 第三区：按钮区（580-690像素，110像素高度）
        self.bottom_frame = QFrame()
        self.bottom_frame.setObjectName("BottomFrame")
        self.bottom_frame.setFixedHeight(110)  # 固定110像素高度
        bottom_layout = QVBoxLayout(self.bottom_frame)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(0)
        
        # 按钮区将使用QStackedWidget来切换主界面和播放列表按钮
        self.button_stack = QStackedWidget()
        self.button_stack.setObjectName("ButtonStack")
        
        # 将内容区和按钮区添加到根布局
        content_layout.addWidget(self.content_stack)
        bottom_layout.addWidget(self.button_stack)
        
        root.addWidget(self.content_frame)
        root.addWidget(self.bottom_frame)
        
        # 现在初始化主界面和播放列表界面的具体内容
        self._init_main_content()
        self._init_playlist_content()
        self._init_main_buttons()
        self._init_playlist_buttons()
        
        # 设置初始状态
        self.content_stack.setCurrentIndex(0)  # 主界面内容
        self.button_stack.setCurrentIndex(0)   # 主界面按钮
        self.lbl_title.setText("TTplayer")     # 主界面标题

    def _init_main_content(self):
        """初始化主界面内容"""
        # 获取已在 _init_ui 中创建的布局
        main_content_layout = self.main_content.layout()
        
        # 歌名标签
        self.lbl_info = QLabel("无正在播放歌曲")
        self.lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_info.setStyleSheet("font-size: 14px; font-weight: bold; margin-bottom: 6px;")
        
        # 黑胶唱片
        self.vinyl = VinylCover(self)
        
        # 像素信息显示
        self.telemetry_panel = QWidget()
        self.telemetry_panel.setObjectName("TelemetryPanel")
        self.telemetry_panel.setFixedHeight(58)
        telemetry_layout = QHBoxLayout(self.telemetry_panel)
        telemetry_layout.setContentsMargins(0, 5, 0, 5)
        telemetry_layout.setSpacing(2)

        self.info_container = QWidget(self.telemetry_panel)
        self.info_container.setObjectName("DotInfoContainer")
        self.info_container.setFixedWidth(240)
        info_layout = QVBoxLayout(self.info_container)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(1)

        self.info_line_top = DotMatrixLabel()
        self.info_line_top.setObjectName("InfoLineTop")
        self.info_line_top.setTextFormat(Qt.TextFormat.RichText)
        self.info_line_top.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.info_line_bottom = DotMatrixLabel()
        self.info_line_bottom.setObjectName("InfoLineBottom")
        self.info_line_bottom.setTextFormat(Qt.TextFormat.RichText)
        self.info_line_bottom.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        dot_font = self._build_dot_matrix_font()
        self.info_line_top.setFont(dot_font)
        self.info_line_bottom.setFont(dot_font)
        self.info_line_top.setFixedWidth(240)
        self.info_line_bottom.setFixedWidth(240)
        self._info_line_top_glow = QGraphicsDropShadowEffect(self.info_line_top)
        self._info_line_top_glow.setBlurRadius(6.0)
        self._info_line_top_glow.setOffset(0, 0)
        self.info_line_top.setGraphicsEffect(self._info_line_top_glow)
        self._info_line_bottom_glow = QGraphicsDropShadowEffect(self.info_line_bottom)
        self._info_line_bottom_glow.setBlurRadius(6.0)
        self._info_line_bottom_glow.setOffset(0, 0)
        self.info_line_bottom.setGraphicsEffect(self._info_line_bottom_glow)
        info_layout.addWidget(self.info_line_top)
        info_layout.addWidget(self.info_line_bottom)

        self.spectrum_widget = SpectrumWidget(self.telemetry_panel)
        self.spectrum_widget.setFixedWidth(120)

        telemetry_layout.addWidget(self.info_container)
        telemetry_layout.addWidget(self.spectrum_widget)

        # 播放进度条
        self.prog_layout = QHBoxLayout()
        self.prog_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_curr = QLabel("00:00")
        self.slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.lbl_total = QLabel("00:00")
        self.lbl_curr.setFixedHeight(22)
        self.lbl_total.setFixedHeight(22)
        self.slider.setFixedHeight(22)
        self.prog_layout.addWidget(self.lbl_curr)
        self.prog_layout.addWidget(self.slider)
        self.prog_layout.addWidget(self.lbl_total)
        
        # 内嵌歌词显示 - 使用自定义 LyricDisplay 组件
        self.lyrics_display = LyricDisplay()
        
        
        # 更新布局边距和间距
        main_content_layout.setContentsMargins(10, 10, 10, 10)
        main_content_layout.setSpacing(8)
        
        # 将元素添加到主界面内容布局
        main_content_layout.addWidget(self.lbl_info)
        main_content_layout.addWidget(self.vinyl, 0, Qt.AlignmentFlag.AlignHCenter)
        main_content_layout.addWidget(self.lyrics_display)
        main_content_layout.addStretch()  # 将点阵信息区和进度条推到更靠近底部的位置
        main_content_layout.addWidget(self.telemetry_panel)
        main_content_layout.addLayout(self.prog_layout)
        
        # 添加到内容栈
        self.content_stack.addWidget(self.main_content)
        
        # 初始化信息显示
        self._apply_accent_color_bindings()
        self._set_info_bar_default()

    def _init_playlist_content(self):
        """初始化播放列表内容"""
        self.playlist_content = QWidget()
        playlist_content_layout = QVBoxLayout(self.playlist_content)
        playlist_content_layout.setContentsMargins(10, 10, 10, 10)
        playlist_content_layout.setSpacing(0)
        
        # 播放列表
        self.list_widget = QListWidget()
        self.list_widget.setObjectName("PlaylistList")
        self.list_widget.setFrameShape(QFrame.Shape.NoFrame)
        self.list_widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_widget.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list_widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.list_widget.setUniformItemSizes(True)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        playlist_content_layout.addWidget(self.list_widget)
        
        # 添加到内容栈
        self.content_stack.addWidget(self.playlist_content)

    def _init_main_buttons(self):
        """初始化主界面按钮"""
        self.main_buttons = QWidget()
        main_buttons_layout = QHBoxLayout(self.main_buttons)
        main_buttons_layout.setContentsMargins(10, 10, 10, 10)
        main_buttons_layout.setSpacing(10)
        
        # 播放控制按钮
        self.btn_prev = self._create_button(QStyle.StandardPixmap.SP_MediaSkipBackward, "上一首")
        self.btn_play = self._create_button(QStyle.StandardPixmap.SP_MediaPlay, "播放")
        self.btn_play.setObjectName("PlayButton")
        self.btn_play.setFixedSize(56, 56)
        self.btn_play.setIconSize(QSize(36, 36))
        self.btn_pause = self._create_button(QStyle.StandardPixmap.SP_MediaPause, "暂停")
        self.btn_pause.setObjectName("PlayButton")
        self.btn_pause.setFixedSize(56, 56)
        self.btn_pause.setIconSize(QSize(36, 36))
        self.btn_next = self._create_button(QStyle.StandardPixmap.SP_MediaSkipForward, "下一首")
        
        # 音量控制
        self.volume_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.volume_slider.setObjectName("VolumeSlider")
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.setFixedSize(50, 24)
        
        # 添加歌曲按钮
        self.btn_add_songs = self._create_button(QStyle.StandardPixmap.SP_DirIcon, "添加歌曲")
        
        # 切换视图按钮
        self.btn_view = self._create_button(QStyle.StandardPixmap.SP_FileDialogDetailedView, "切换视图")
        
        # 播放控制组
        media_ctrl_layout = QHBoxLayout()
        media_ctrl_layout.setSpacing(4)
        media_ctrl_layout.setContentsMargins(0, 0, 0, 0)
        
        # 播放/暂停切换
        self._play_toggle_host = QWidget()
        self._play_toggle_host.setFixedSize(56, 56)
        self._play_toggle_layout = QStackedLayout(self._play_toggle_host)
        self._play_toggle_layout.setContentsMargins(0, 0, 0, 0)
        self._play_toggle_layout.addWidget(self.btn_play)
        self._play_toggle_layout.addWidget(self.btn_pause)
        self._play_toggle_layout.setCurrentWidget(self.btn_play)
        
        media_ctrl_layout.addWidget(self.btn_prev)
        media_ctrl_layout.addWidget(self._play_toggle_host)
        media_ctrl_layout.addWidget(self.btn_next)
        
        # 主布局
        main_buttons_layout.addStretch()
        main_buttons_layout.addLayout(media_ctrl_layout)
        main_buttons_layout.addStretch()
        main_buttons_layout.addWidget(self.volume_slider)
        main_buttons_layout.addWidget(self.btn_add_songs)
        main_buttons_layout.addWidget(self.btn_view)
        main_buttons_layout.addStretch()
        
        # 添加到按钮栈
        self.button_stack.addWidget(self.main_buttons)
        
        # 连接信号
        self.btn_play.clicked.connect(self._toggle_play)
        self.btn_pause.clicked.connect(self._toggle_play)
        self.btn_prev.clicked.connect(self._prev)
        self.btn_next.clicked.connect(self._next)
        self.btn_add_songs.clicked.connect(self._add_files)
        self.btn_view.clicked.connect(self._switch_view)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)

    def _init_playlist_buttons(self):
        """初始化播放列表按钮"""
        self.playlist_buttons = QWidget()
        playlist_buttons_layout = QHBoxLayout(self.playlist_buttons)
        playlist_buttons_layout.setContentsMargins(10, 10, 10, 10)
        playlist_buttons_layout.setSpacing(10)
        
        # 返回按钮
        self.playlist_btn_back = self._create_button(QStyle.StandardPixmap.SP_ArrowLeft, "返回主界面")
        
        playlist_buttons_layout.addStretch()
        playlist_buttons_layout.addWidget(self.playlist_btn_back)
        playlist_buttons_layout.addStretch()
        
        # 添加到按钮栈
        self.button_stack.addWidget(self.playlist_buttons)
        
        # 连接信号
        self.playlist_btn_back.clicked.connect(self._switch_view)

    def _switch_view(self):
        """切换主界面和播放列表之间的视图"""
        current_index = self.content_stack.currentIndex()
        new_index = 1 - current_index  # 在0和1之间切换
        
        # 切换内容
        self.content_stack.setCurrentIndex(new_index)
        self.button_stack.setCurrentIndex(new_index)
        
        # 更新标题
        if new_index == 0:  # 主界面
            self.lbl_title.setText("TTplayer")
            self._view_mode = 0
        else:  # 播放列表
            self.lbl_title.setText("播放列表")
            self._view_mode = 1
            
            # 确保列表滚动到顶部
            if hasattr(self, 'list_widget') and self.list_widget.count() > 0:
                self.list_widget.scrollToTop()
                if self.list_widget.currentRow() < 0:
                    self.list_widget.setCurrentRow(0)
        
        self._save_app_state()

    def _show_playlist_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if item is not None:
            self.list_widget.setCurrentItem(item)
        menu = QMenu(self.list_widget)
        remove_action = menu.addAction("删除")
        up_action = menu.addAction("上移")
        down_action = menu.addAction("下移")
        menu.addSeparator()
        clear_action = menu.addAction("清空歌单")
        menu.addSeparator()
        policy_menu = menu.addMenu("删除当前曲目后")
        policy_next = policy_menu.addAction("自动下一首")
        policy_next.setCheckable(True)
        policy_next.setChecked(self._remove_behavior == "next")
        policy_stop = policy_menu.addAction("停止播放")
        policy_stop.setCheckable(True)
        policy_stop.setChecked(self._remove_behavior == "stop")

        action = menu.exec(self.list_widget.mapToGlobal(pos))
        if action == remove_action:
            self._remove_selected_file()
        elif action == up_action:
            self._move_selected_up()
        elif action == down_action:
            self._move_selected_down()
        elif action == clear_action:
            self._clear_playlist()
        elif action == policy_next:
            self._remove_behavior = "next"
            self._save_app_state()
        elif action == policy_stop:
            self._remove_behavior = "stop"
            self._save_app_state()

    def _clear_playlist(self):
        self.playlist_files.clear()
        self.list_widget.clear()
        self._current_index = -1
        self._player.stop()
        self._timer.stop()
        self.lbl_info.setText("无正在播放歌曲")
        self._set_info_bar_default()
        if hasattr(self, "spectrum_widget"):
            self.spectrum_widget.set_active(False)
        self._set_lyrics_status("暂无歌词")
        self._save_playlist_to_disk()

    def _adjust_lyrics_offset(self, delta_ms: int):
        self._lyrics_offset_ms = max(-5000, min(5000, self._lyrics_offset_ms + delta_ms))
        self._last_lyric_index = -1
        self._update_lyrics(self._player.position())
        self._save_app_state()

    def _set_lyrics_status(self, text: str):
        """Set lyrics status message (for embedded display)"""
        if hasattr(self, 'lyrics_display'):
            self.lyrics_display.set_status(text)
        self._last_lyric_index = -2
    
    def _load_lyrics_to_embedded_display(self):
        """Load lyrics into embedded display using new LyricDisplay component"""
        if not hasattr(self, 'lyrics_display'):
            return
        
        if not hasattr(self, "_current_lrc") or not self._current_lrc:
            self._set_lyrics_status("暂无歌词")
            return
        if not self._current_lrc.lyrics:
            self._set_lyrics_status("暂无歌词")
            return
        
        # 使用新的 LyricDisplay 组件 API
        self.lyrics_display.set_lyrics(self._current_lrc.lyrics)
        self._last_lyric_index = -1
        
        # 更新主题颜色
        self._refresh_embedded_lyrics_styles()

    def _refresh_embedded_lyrics_styles(self):
        """Refresh embedded lyrics display styles based on current theme"""
        if not hasattr(self, 'lyrics_display'):
            return
        # 更新强调色和背景色
        accent = self._get_current_accent_color()
        self.lyrics_display.set_accent_color(accent)
        
        # 获取当前主题的背景色
        theme_name = getattr(self, "current_theme", "自适应")
        active_palette = getattr(self, "_active_theme_palette", None)
        palette = active_palette if theme_name == "自适应" else None
        t = ThemeManager.resolve(theme_name, palette)
        bg_color = QColor(t.get("panel", "#1E293B"))
        self.lyrics_display.set_bg_color(bg_color)

    def _get_current_accent_color(self) -> QColor:
        theme_name = getattr(self, "current_theme", "自适应")
        active_palette = getattr(self, "_active_theme_palette", None)
        palette = active_palette if theme_name == "自适应" else None
        t = ThemeManager.resolve(theme_name, palette)
        accent = QColor(t.get("accent", "#A7F3D0"))
        if accent.isValid():
            return accent
        return QColor(getattr(self, "current_accent_color", QColor("#A7F3D0")))

    def _update_current_accent_color(self):
        self.current_accent_color = self._get_current_accent_color()

    def _apply_accent_color_bindings(self):
        accent = self._get_current_accent_color()
        accent_css = accent.name()
        if hasattr(self, "info_line_top"):
            self.info_line_top.setStyleSheet(f"color: {accent_css};")
        if hasattr(self, "info_line_bottom"):
            self.info_line_bottom.setStyleSheet(f"color: {accent_css};")
        if hasattr(self, "_info_line_top_glow"):
            glow_top = QColor(0, 0, 0, 170)
            self._info_line_top_glow.setColor(glow_top)
        if hasattr(self, "_info_line_bottom_glow"):
            glow_bottom = QColor(0, 0, 0, 170)
            self._info_line_bottom_glow.setColor(glow_bottom)
        if hasattr(self, "spectrum_widget"):
            self.spectrum_widget.set_accent_color(accent)

    def _set_info_bar_default(self):
        if not hasattr(self, "info_line_top") or not hasattr(self, "info_line_bottom"):
            return
        accent = self._get_current_accent_color()
        accent_css = accent.name()
        border = f"rgba({accent.red()}, {accent.green()}, {accent.blue()}, 0.88)"
        dot_family = getattr(self, "_dot_font_family", "Consolas")
        self.info_line_top.setText(
            f"<span style='line-height:1.05; color:{accent_css}; font-family:\"{dot_family}\";'>"
            f"<span style='border:1px solid {border}; border-radius:3px; padding:0 3px;'>---</span> | --"
            f"</span>"
        )
        self.info_line_bottom.setText(
            f"<span style='line-height:1.05; color:{accent_css}; font-family:\"{dot_family}\";'>-- kbps | -- kHz</span>"
        )
        self.info_line_top.repaint()
        self.info_line_bottom.repaint()

    def _update_info_bar_from_path(self, path: str):
        if not hasattr(self, "info_line_top") or not hasattr(self, "info_line_bottom"):
            return
        accent = self._get_current_accent_color()
        accent_css = accent.name()
        border = f"rgba({accent.red()}, {accent.green()}, {accent.blue()}, 0.88)"
        dot_family = getattr(self, "_dot_font_family", "Consolas")
        fmt = Path(path).suffix.replace(".", "").upper() or "AUDIO"
        bitrate_txt = "-- kbps"
        sample_txt = "-- kHz"
        channel_txt = "--"
        if MUTAGEN_AVAILABLE and File is not None:
            try:
                audio = File(path)
                info = getattr(audio, "info", None)
                if info is not None:
                    bitrate = int(getattr(info, "bitrate", 0) / 1000)
                    sample_rate = float(getattr(info, "sample_rate", 0)) / 1000.0
                    channels = int(getattr(info, "channels", 0) or 0)
                    if bitrate > 0:
                        bitrate_txt = f"{bitrate} kbps"
                    if sample_rate > 0:
                        sample_txt = f"{sample_rate:.1f} kHz"
                    if channels == 2:
                        channel_txt = "STEREO"
                    elif channels == 1:
                        channel_txt = "MONO"
                    elif channels > 2:
                        channel_txt = f"{channels} CH"
            except MUTAGEN_ERRORS as exc:
                logger.debug("Info bar parse failed for %s: %s", path, exc)
        line1 = (
            f"<span style='line-height:1.05; color:{accent_css}; font-family:\"{dot_family}\";'>"
            f"<span style='border:1px solid {border}; border-radius:3px; padding:0 3px;'>"
            f"{escape(fmt)}</span> | {channel_txt}</span>"
        )
        line2 = (
            f"<span style='line-height:1.05; color:{accent_css}; font-family:\"{dot_family}\";'>"
            f"{bitrate_txt} | {sample_txt}</span>"
        )
        self.info_line_top.setText(line1)
        self.info_line_bottom.setText(line2)
        self.info_line_top.repaint()
        self.info_line_bottom.repaint()


    def _apply_button_shadows(self):
        """应用按钮的阴影效果"""
        # 获取当前主题的强调色
        theme_data = ThemeManager.resolve(self.current_theme, self._active_theme_palette if self.current_theme == "自适应" else None)
        accent_color = QColor(theme_data["accent"])
        accent_darker = accent_color.darker(140)
        
        # ControlButton阴影 - 中等深度
        for btn in [self.btn_prev, self.btn_next, self.btn_view, self.btn_add_songs]:
            if btn:
                shadow = QGraphicsDropShadowEffect()
                shadow.setBlurRadius(6)
                shadow.setColor(accent_darker)
                shadow.setOffset(0, 2)
                shadow.setColor(QColor(accent_darker.red(), accent_darker.green(), 
                                      accent_darker.blue(), int(255 * 0.25)))
                btn.setGraphicsEffect(shadow)
        
        # PlayButton阴影 - 更深的效果
        for btn in [self.btn_play, self.btn_pause]:
            if btn:
                shadow = QGraphicsDropShadowEffect()
                shadow.setBlurRadius(8)
                shadow.setColor(accent_darker)
                shadow.setOffset(0, 3)
                shadow.setColor(QColor(accent_darker.red(), accent_darker.green(), 
                                      accent_darker.blue(), int(255 * 0.30)))
                btn.setGraphicsEffect(shadow)
        
        # TopButton - 无阴影或轻微阴影
        for btn in [self.btn_theme, self.btn_min, self.btn_close]:
            if btn:
                # 不设置阴影
                btn.setGraphicsEffect(None)
        
        # 播放列表按钮阴影 - 只保留返回按钮
        playlist_buttons = []
        if hasattr(self, 'playlist_btn_back'):
            playlist_buttons.append(self.playlist_btn_back)
        
        for btn in playlist_buttons:
            if btn:
                shadow = QGraphicsDropShadowEffect()
                shadow.setBlurRadius(6)
                shadow.setColor(accent_darker)
                shadow.setOffset(0, 2)
                shadow.setColor(QColor(accent_darker.red(), accent_darker.green(), 
                                      accent_darker.blue(), int(255 * 0.25)))
                btn.setGraphicsEffect(shadow)

    def apply_theme(self, name):
        if name not in ThemeManager.THEMES:
            name = "自适应"
        self.current_theme = name
        palette = self._active_theme_palette if name == "自适应" else None
        style = ThemeManager.get_style(name, palette)
        self.setStyleSheet(style)
        self._apply_button_shadows()  # 应用按钮阴影效果
        self._update_current_accent_color()
        self._apply_accent_color_bindings()
        if hasattr(self, "info_line_top"):
            idx = int(getattr(self, "_current_index", -1))
            files = getattr(self, "playlist_files", [])
            if 0 <= idx < len(files):
                self._update_info_bar_from_path(files[idx])
            else:
                self._set_info_bar_default()
        self._refresh_media_control_button_styles()
        self._refresh_button_icons()
        self._refresh_embedded_lyrics_styles()
        if hasattr(self, "_state_store"):
            self._save_app_state()
        # self.btn_vol_meter.setAccent(t_data["accent"]) # StealthVolumeMeter removed

    def eventFilter(self, watched, event):
        if isinstance(watched, QPushButton) and watched in {
            getattr(self, "btn_prev", None),
            getattr(self, "btn_play", None),
            getattr(self, "btn_pause", None),
            getattr(self, "btn_next", None),
        }:
            if event.type() == QEvent.Type.Enter:
                self._set_button_glow(watched, True)
            elif event.type() in (QEvent.Type.Leave, QEvent.Type.Hide):
                self._set_button_glow(watched, False)
        return super().eventFilter(watched, event)

    def _extract_cover_dominant_color(self, pixmap: QPixmap) -> QColor:
        if pixmap.isNull():
            return QColor("#0B1220")
        image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGB32)
        thumb = image.scaled(
            16,
            16,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        total_r = 0
        total_g = 0
        total_b = 0
        count = thumb.width() * thumb.height()
        for y in range(thumb.height()):
            for x in range(thumb.width()):
                c = thumb.pixelColor(x, y)
                total_r += c.red()
                total_g += c.green()
                total_b += c.blue()
        if count <= 0:
            return QColor("#0B1220")
        return QColor(total_r // count, total_g // count, total_b // count)

    def _ensure_bg_readable(self, color: QColor) -> QColor:
        # Keep background in a darker range so white text/lyrics stay readable.
        luminance = 0.2126 * color.red() + 0.7152 * color.green() + 0.0722 * color.blue()
        if luminance > 150:
            return color.darker(220)
        if luminance > 110:
            return color.darker(150)
        return color

    def _on_bg_anim_value_changed(self, value):
        if not isinstance(value, QColor):
            return
        self._active_theme_palette = ThemeManager.build_adaptive_palette(value)
        if self.current_theme == "自适应":
            self.apply_theme(self.current_theme)

    def _set_adaptive_background(self, cover_pixmap: QPixmap | None, animate: bool = True):
        if not cover_pixmap or cover_pixmap.isNull():
            self._bg_anim.stop()
            self._bg_from_color = QColor(self._default_seed_color)
            self._bg_to_color = QColor(self._default_seed_color)
            self._active_theme_palette = ThemeManager.build_adaptive_palette(self._default_seed_color)
            if self.current_theme == "自适应":
                self.apply_theme(self.current_theme)
            return
        target = self._extract_cover_dominant_color(cover_pixmap)
        target = self._ensure_bg_readable(target)
        if self.current_theme != "自适应":
            self._bg_to_color = target
            self._active_theme_palette = ThemeManager.build_adaptive_palette(target)
            return
        if not animate:
            self._bg_to_color = target
            self._active_theme_palette = ThemeManager.build_adaptive_palette(target)
            self.apply_theme(self.current_theme)
            return
        self._bg_anim.stop()
        start = QColor(self._bg_to_color)
        self._bg_from_color = start
        self._bg_to_color = target
        self._bg_anim.setStartValue(start)
        self._bg_anim.setEndValue(target)
        self._bg_anim.start()

    def _connect_signals(self):
        # 注意：主界面按钮信号（btn_prev, btn_next, btn_view, btn_add_songs, volume_slider）
        # 已在 _init_main_buttons 中连接，避免重复连接

        # 播放列表右键菜单
        self.list_widget.customContextMenuRequested.connect(self._show_playlist_context_menu)
        self.list_widget.itemDoubleClicked.connect(self._on_item_dbl_click)

        # 进度条控制
        self.slider.sliderPressed.connect(self._player.pause)
        self.slider.sliderReleased.connect(self._player.play)
        self.slider.sliderMoved.connect(lambda v: self._player.setPosition(v * 1000))

        # 播放器信号
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_state_changed)
        self._player.metaDataChanged.connect(self._on_metadata_changed)

    # Logic

    def _on_metadata_changed(self):
        self._on_meta_changed()

    def _on_meta_changed(self):
        if 0 <= self._current_index < len(self.playlist_files):
            self._update_info_bar_from_path(self.playlist_files[self._current_index])
        # Fallback if mutagen failed or is missing
        if not MUTAGEN_AVAILABLE or not self._current_lrc:
            meta = self._player.metaData()

            title = meta.value(QMediaMetaData.Key.Title)
            artist = meta.value(QMediaMetaData.Key.ContributingArtist)

            # Update Info Label if needed
            if title:
                display = f"{artist} - {title}" if artist else str(title)
                self.lbl_info.setText(display)

            # Try to get Lyrics (Qt/PyQt versions expose different metadata keys)
            lyrics = None
            lyric_key_names = ("Lyrics", "Lyricist", "Comment", "Description")
            for key_name in lyric_key_names:
                key = getattr(QMediaMetaData.Key, key_name, None)
                if key is None:
                    continue
                value = meta.value(key)
                if value:
                    lyrics = value
                    break

            if lyrics:
                self._current_lrc = LrcParser(str(lyrics), is_text=True)
                self._load_lyrics_to_embedded_display()
                self._update_lyrics(self._player.position())

            # Try to get Cover Art
            cover = meta.value(QMediaMetaData.Key.ThumbnailImage) or meta.value(
                QMediaMetaData.Key.CoverArtImage
            )
            if cover and isinstance(cover, QImage):
                pm = QPixmap.fromImage(cover)
                self.vinyl.set_cover(pm)
                self._set_adaptive_background(pm, animate=True)
            elif cover and isinstance(cover, QPixmap):
                self.vinyl.set_cover(cover)
                self._set_adaptive_background(cover, animate=True)
            else:
                self.vinyl.set_cover(None)
                self._set_adaptive_background(None, animate=False)

    def _toggle_play(self):
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _update_play_btn_state(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            if hasattr(self, "_play_toggle_layout"):
                self._play_toggle_layout.setCurrentWidget(self.btn_pause)
        else:
            if hasattr(self, "_play_toggle_layout"):
                self._play_toggle_layout.setCurrentWidget(self.btn_play)

    def _on_state_changed(self, state):
        self._update_play_btn_state(state)

        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.vinyl.start_anim()
            if hasattr(self, "spectrum_widget"):
                self.spectrum_widget.set_active(True)
            # 启动歌词更新定时器
            if hasattr(self, "_timer"):
                self._timer.start()
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self.vinyl.pause_anim()
            if hasattr(self, "spectrum_widget"):
                self.spectrum_widget.set_active(False)
        else:
            self.vinyl.stop_anim()
            if hasattr(self, "spectrum_widget"):
                self.spectrum_widget.set_active(False)

    def _on_timer(self):
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._update_lyrics(self._player.position())

    def _update_lyrics(self, pos):
        """Update lyrics in the embedded display"""
        if not hasattr(self, "_current_lrc") or not self._current_lrc:
            return
        if not self._current_lrc.lyrics:
            return
        if self._lyrics_lock_line:
            return
        current_idx = self._current_lrc.get_current_index(pos + self._lyrics_offset_ms)
        if current_idx < 0:
            current_idx = 0
        if current_idx == self._last_lyric_index:
            return
        self._last_lyric_index = current_idx
        
        # Update embedded lyrics display using new LyricDisplay component
        if hasattr(self, 'lyrics_display'):
            self.lyrics_display.set_current_index(current_idx, animate=True)

    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "添加歌曲", "", "Audio (*.mp3 *.m4a *.wav *.flac)"
        )
        if files:
            for f in files:
                self.playlist_files.append(f)
            self._refresh_playlist_view()
            if self._current_index == -1 and self.playlist_files:
                self._play_index(0)
            self._save_playlist_to_disk()

    def _format_playlist_item(self, idx: int, path: str) -> str:
        meta = AudioMetadata.from_file(path)
        return f"{idx + 1}. {meta.display_name}"

    def _refresh_playlist_view(self):
        current_row = self.list_widget.currentRow()
        self.list_widget.clear()
        for idx, path in enumerate(self.playlist_files):
            self.list_widget.addItem(self._format_playlist_item(idx, path))
        if self.list_widget.count() > 0:
            row = self._current_index if self._current_index >= 0 else current_row
            row = max(0, min(row, self.list_widget.count() - 1))
            self.list_widget.setCurrentRow(row)

    def _remove_selected_file(self):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self.playlist_files):
            return
        self.playlist_files.pop(row)
        self._refresh_playlist_view()

        if row == self._current_index:
            if self._remove_behavior == "next" and self.playlist_files:
                self._current_index = -1
                next_idx = min(row, len(self.playlist_files) - 1)
                self._play_index(next_idx)
            else:
                self._player.stop()
                self._timer.stop()
                self._current_index = -1
                self.lbl_info.setText("无正在播放歌曲")
                self._set_info_bar_default()
                self._set_lyrics_status("暂无歌词")
        elif row < self._current_index:
            self._current_index -= 1

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(
                max(0, min(row, self.list_widget.count() - 1))
            )
        self._save_playlist_to_disk()

    def _move_selected_up(self):
        row = self.list_widget.currentRow()
        if row <= 0 or row >= len(self.playlist_files):
            return
        self.playlist_files[row - 1], self.playlist_files[row] = (
            self.playlist_files[row],
            self.playlist_files[row - 1],
        )
        self._refresh_playlist_view()
        self.list_widget.setCurrentRow(row - 1)

        if self._current_index == row:
            self._current_index = row - 1
        elif self._current_index == row - 1:
            self._current_index = row
        self._save_playlist_to_disk()

    def _move_selected_down(self):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self.playlist_files) - 1:
            return
        self.playlist_files[row], self.playlist_files[row + 1] = (
            self.playlist_files[row + 1],
            self.playlist_files[row],
        )
        self._refresh_playlist_view()
        self.list_widget.setCurrentRow(row + 1)

        if self._current_index == row:
            self._current_index = row + 1
        elif self._current_index == row + 1:
            self._current_index = row
        self._save_playlist_to_disk()

    def _to_store_path(self, filepath: str) -> str:
        path = Path(filepath)
        try:
            rel = path.resolve().relative_to(self._playlist_root)
            return rel.as_posix()
        except ValueError:
            return str(path.resolve())

    def _resolve_store_path(self, stored: str) -> Path:
        path = Path(stored)
        if not path.is_absolute():
            path = (self._playlist_root / path).resolve()
        else:
            path = path.resolve()
        return path

    def _atomic_write_text(self, path: Path, content: str):
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

    def _save_playlist_to_disk(self):
        try:
            lines = ["#EXTM3U", f"#CURRENT:{self._current_index}"]
            for f in self.playlist_files:
                lines.append(self._to_store_path(f))
            self._atomic_write_text(self._playlist_store, "\n".join(lines) + "\n")
        except (OSError, UnicodeError, ValueError) as exc:
            logger.error("Saving playlist failed: %s", exc)

    def _load_playlist_from_disk(self):
        if not self._playlist_store.exists():
            return
        try:
            lines = self._playlist_store.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            logger.error("Loading playlist failed: %s", exc)
            return

        files: list[str] = []
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

        self.playlist_files = []
        self.list_widget.clear()
        for f in files:
            if not isinstance(f, str):
                continue
            resolved = self._resolve_store_path(f)
            if resolved.exists():
                fp = str(resolved)
                self.playlist_files.append(fp)
        self._refresh_playlist_view()

        if 0 <= saved_idx < len(self.playlist_files):
            self._current_index = saved_idx
            self.list_widget.setCurrentRow(saved_idx)

    def _save_app_state(self):
        if not getattr(self, "_init_done", False):
            return
        state = {
            "current_index": self._current_index,
            "position_ms": int(self._player.position()) if hasattr(self, "_player") else 0,
            "volume": int(self.volume_slider.value()) if hasattr(self, "volume_slider") else 50,
            "theme": self.current_theme,
            "view_mode": self._view_mode,
            "remove_behavior": self._remove_behavior,
            "lyrics_follow": self._lyrics_follow_enabled,
            "lyrics_lock": self._lyrics_lock_line,
            "lyrics_offset_ms": self._lyrics_offset_ms,
        }
        try:
            self._atomic_write_text(
                self._state_store,
                json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            )
        except (OSError, ValueError, TypeError) as exc:
            logger.error("Saving app state failed: %s", exc)

    def _load_app_state(self):
        if not self._state_store.exists():
            self._pending_restore_view_mode = 0  # 默认显示主界面
            return
        try:
            state = json.loads(self._state_store.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            logger.error("Loading app state failed: %s", exc)
            self._pending_restore_view_mode = 0  # 默认显示主界面
            return

        saved_theme = str(state.get("theme", self.current_theme))
        if saved_theme not in ThemeManager.THEMES:
            saved_theme = "自适应"
        self.current_theme = saved_theme
        self.apply_theme(self.current_theme)

        vol = int(state.get("volume", 50))
        vol = max(0, min(100, vol))
        self.volume_slider.setValue(vol)
        self._on_volume_changed(vol)

        self._remove_behavior = str(state.get("remove_behavior", self._remove_behavior))
        if self._remove_behavior not in {"next", "stop"}:
            self._remove_behavior = "next"

        self._lyrics_follow_enabled = bool(state.get("lyrics_follow", True))
        self._lyrics_lock_line = bool(state.get("lyrics_lock", False))
        self._lyrics_offset_ms = int(state.get("lyrics_offset_ms", 0))
        self._resume_position_ms = max(0, int(state.get("position_ms", 0)))
        self._current_index = int(state.get("current_index", -1))
        # 无论退出时是什么状态，启动时强制进入主界面
        self._pending_restore_view_mode = 0

    def _apply_restored_view_mode(self):
        mode = self._pending_restore_view_mode
        if mode is None:
            mode = 0
        self._pending_restore_view_mode = None
        self._set_view_mode(mode)

    def _restore_last_track(self):
        if 0 <= self._current_index < len(self.playlist_files):
            self._play_index(
                self._current_index,
                autoplay=False,
                start_pos_ms=self._resume_position_ms,
            )

    def _set_view_mode(self, mode: int):
        mode = int(mode)
        if mode not in (0, 1, 2):
            mode = 2
        self._view_mode = mode
        # 使用 content_stack 和 button_stack 来切换视图
        if mode == 0:  # 主界面
            self.content_stack.setCurrentIndex(0)
            self.button_stack.setCurrentIndex(0)
            self.lbl_title.setText("TTplayer")
        elif mode == 1:  # 播放列表
            self.content_stack.setCurrentIndex(1)
            self.button_stack.setCurrentIndex(1)
            self.lbl_title.setText("播放列表")
        # Mode 2 (hidden) is no longer used

    def _play_index(self, idx, autoplay: bool = True, start_pos_ms: int = 0):
        if 0 <= idx < len(self.playlist_files):
            self._current_index = idx
            self.list_widget.setCurrentRow(idx)
            path = self.playlist_files[idx]
            self._player.setSource(QUrl.fromLocalFile(path))
            if autoplay:
                self._player.play()
                self._timer.start()
            else:
                self._player.pause()
                self._timer.stop()
                if start_pos_ms > 0:
                    self._player.setPosition(start_pos_ms)

            # Update Meta
            meta = AudioMetadata.from_file(path)
            self.lbl_info.setText(meta.display_name)
            self._update_info_bar_from_path(path)

            # Update Cover
            if meta.cover_data:
                pm = QPixmap()
                pm.loadFromData(meta.cover_data)
                self.vinyl.set_cover(pm)
                self._set_adaptive_background(pm, animate=True)
            else:
                self.vinyl.set_cover(None)  # Default
                self._set_adaptive_background(None, animate=False)

            # Update Lyrics
            self._current_lrc = None

            # Priority 1: Local .lrc file (Most reliable)
            lrc_path = os.path.splitext(path)[0] + ".lrc"
            if os.path.exists(lrc_path):
                logger.debug("Loading local lyrics: %s", lrc_path)
                self._current_lrc = LrcParser(lrc_path)

            # Priority 2: Embedded Lyrics (Mutagen)
            elif meta.lyrics_text:
                self._current_lrc = LrcParser(meta.lyrics_text, is_text=True)

            if not self._current_lrc:
                self._set_lyrics_status("暂无歌词")
            else:
                self._load_lyrics_to_embedded_display()
                self._update_lyrics(0)
            self._save_playlist_to_disk()
            self._save_app_state()

    def _prev(self):
        if self._current_index > 0:
            self._play_index(self._current_index - 1)

    def _next(self):
        if self._current_index < len(self.playlist_files) - 1:
            self._play_index(self._current_index + 1)

    def _on_position_changed(self, ms):
        self._resume_position_ms = int(ms)
        if not self.slider.isSliderDown():
            self.slider.setValue(ms // 1000)
        self.lbl_curr.setText(f"{ms // 60000:02d}:{(ms // 1000) % 60:02d}")

    def _on_duration_changed(self, ms):
        self.slider.setMaximum(ms // 1000)
        self.lbl_total.setText(f"{ms // 60000:02d}:{(ms // 1000) % 60:02d}")

    def _on_item_dbl_click(self, item):
        idx = self.list_widget.row(item)
        self._play_index(idx)

    # Window Dragging
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )

    def mouseMoveEvent(self, e):
        if self._drag_pos:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None

    def _on_volume_changed(self, value):
        self._audio_output.setVolume(value / 100.0)

    def closeEvent(self, event):
        self._save_playlist_to_disk()
        self._save_app_state()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainPlayer()
    w.show()
    sys.exit(app.exec())