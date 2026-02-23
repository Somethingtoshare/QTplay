"""
ui_helpers.py - UI 辅助函数

包含与 UI 组件相关的独立函数：按钮创建/图标适配、点阵字体加载、按钮样式与发光效果。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from PyQt6.QtGui import QFont, QFontDatabase, QIcon, QPainter, QPixmap
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QPushButton, QStyle, QGraphicsDropShadowEffect, QWidget
from PyQt6.QtCore import QSize, Qt

from utils import get_resource_path


def build_dot_matrix_font() -> Tuple[QFont, str, Optional[Path]]:
    font_family = None
    font_source = None
    font_candidates = [
        "Assets/VT323/VT323-Regular.ttf",
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
    return font, font.family(), font_source


def _fit_icon_canvas(pixmap: QPixmap, target: QSize) -> QPixmap:
    if pixmap.isNull() or not target.isValid():
        return pixmap
    src = pixmap
    dpr = src.devicePixelRatio()
    if dpr and abs(dpr - 1.0) > 1e-6:
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


def apply_button_icon(btn: QPushButton, parent_widget: Optional[QWidget] = None) -> None:
    icon_source = getattr(btn, "_icon_source", None)
    if icon_source is None:
        return
    size = btn.iconSize()
    if isinstance(icon_source, QStyle.StandardPixmap):
        style = parent_widget.style() if parent_widget is not None else None
        if not style:
            return
        raw_icon = style.standardIcon(icon_source)
        fitted = _fit_icon_canvas(raw_icon.pixmap(size), size)
        btn.setIcon(QIcon(fitted))
        return
    if isinstance(icon_source, QPixmap):
        src = _fit_icon_canvas(icon_source, size)
        btn.setIcon(QIcon(src))
        return
    btn.setIcon(QIcon())


def create_button(icon_source, tooltip: str, parent_widget: Optional[QWidget] = None) -> QPushButton:
    btn = QPushButton()
    btn.setObjectName("ControlButton")
    setattr(btn, "_icon_source", icon_source)
    btn.setIconSize(QSize(32, 32))
    apply_button_icon(btn, parent_widget)
    btn.setFixedSize(48, 48)
    btn.setToolTip(tooltip)
    return btn


def apply_button_style(button: QPushButton, accent_color: QColor) -> None:
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


def set_button_glow(button: QPushButton, enabled: bool) -> None:
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
