"""
theme_manager.py - 主题管理器
"""

import json
from pathlib import Path
from PyQt6.QtGui import QColor


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

