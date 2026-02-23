"""
widgets.py - 自定义 UI 组件
"""

import math
import random
import time

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    QTimer,
    pyqtProperty,
)
from PyQt6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPixmap,
    QTextDocument,
    QAbstractTextDocumentLayout,
)
from PyQt6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QLabel,
    QSlider,
    QWidget,
)


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

    rotation = pyqtProperty(float, get_rotation, set_rotation)

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
    
    scroll_offset = pyqtProperty(float, get_scroll_offset, set_scroll_offset)
    
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