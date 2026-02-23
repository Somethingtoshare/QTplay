"""
main.py - 飞羽播放器 (基于Qt的音乐播放器)
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
from component_lyrics_parser import LrcParser  # 歌词解析器
from component_metadata import (
    AudioMetadata,
    MUTAGEN_AVAILABLE,
    MUTAGEN_ERRORS,
    File,
    MP3,
    MP4,
    ID3,
    APIC,
)
from utils import PlatformCompat, get_resource_path
from app_state import save_state, load_state
from playlist_manager import PlaylistManager
from app_controller import AppController
from ui_helpers import (
    create_button,
    build_dot_matrix_font,
    apply_button_icon,
    apply_button_style,
    set_button_glow,
)
from component_widgets import ClickableSlider,VinylCover,DotMatrixLabel,SpectrumWidget,LyricDisplay  # 视觉组件：黑胶唱片、滑块、点阵信息、点阵光柱、歌词渲染
from component_theme_manager import ThemeManager  # 主题管理器

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


# 使用已有组件模块中的平台兼容与资源路径实现，以及 mutagen 可用性常量


# 主题管理器

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
        self.setWindowTitle("飞羽播放器 v1.0")

        # 根据平台加载应用图标（mac 使用 .icns，Windows/Linux 使用 .ico）
        try:
            if sys.platform.startswith("darwin"):
                _icon = get_resource_path("Assets/app_icon.icns")
            else:
                _icon = get_resource_path("Assets/app_icon.ico")
            if Path(_icon).exists():
                self.setWindowIcon(QIcon(str(_icon)))
        except Exception:
            pass

        # 初始化 UI
        self._init_ui()

        # 播放核心
        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)
        self._playlist_root = PlatformCompat.get_storage_dir(
            "飞羽播放器", Path(__file__).resolve().parent
        )
        try:
            self._playlist_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.error("Failed to create storage directory %s: %s", self._playlist_root, exc)
        self._playlist_store = self._playlist_root / "playlist.m3u"
        self._state_store = self._playlist_root / "playlist_state.json"

        # 提前初始化播放列表管理器，避免在 apply_theme() 中访问未创建的属性
        self.playlist_manager = PlaylistManager(app_name="飞羽播放器", dev_dir=self._playlist_root)
        self._current_index = self.playlist_manager.current_index
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

        # 将信号绑定委托给 AppController 以便解耦
        self.controller = AppController(self)

        # 状态
        self._drag_pos = None
        self._view_mode = 0  # 0: Main, 1: Playlist
        self._base_window_width = 388
        self._pending_restore_view_mode: int | None = None
        self._last_lyric_index = -2  # 初始化歌词索引
        self._load_app_state()
        # 刷新本地播放列表视图
        self.playlist_files = self.playlist_manager.files
        self._refresh_playlist_view()
        self._restore_last_track()
        QTimer.singleShot(0, self._apply_restored_view_mode)
        self._init_done = True

    def _create_button(self, icon_source, tooltip):
        return create_button(icon_source, tooltip, parent_widget=self)

    def _build_dot_matrix_font(self) -> QFont:
        font, family, source = build_dot_matrix_font()
        self._dot_font_family = family
        if source is not None:
            logger.info("Dot matrix font loaded: %s (%s)", self._dot_font_family, source)
        else:
            logger.warning("Dot matrix font fallback in use: %s", self._dot_font_family)
        return font

    def _apply_button_icon(self, btn: QPushButton):
        apply_button_icon(btn, parent_widget=self)

    def apply_button_style(self, button: QPushButton, accent_color: QColor):
        apply_button_style(button, accent_color)

    def _set_button_glow(self, button: QPushButton, enabled: bool):
        set_button_glow(button, enabled)

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
                apply_button_icon(btn, parent_widget=self)

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
        
        # 标题文字 - 飞羽播放器（主界面）或播放列表（播放列表界面）
        self.lbl_title = QLabel("飞羽播放器")
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
        self.lbl_title.setText("飞羽播放器")     # 主界面标题

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
            self.lbl_title.setText("飞羽播放器")
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
            files = getattr(self.playlist_manager, "files", [])
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

    # 信号绑定由 app_controller.AppController 管理以实现更好的解耦

    # Logic

    def _on_metadata_changed(self):
        self._on_meta_changed()

    def _on_meta_changed(self):
        if 0 <= self._current_index < len(getattr(self.playlist_manager, 'files', [])):
            path = self.playlist_manager.get_file(self._current_index)
            if path:
                self._update_info_bar_from_path(path)
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
        return getattr(self, 'controller', None) and self.controller.toggle_play()

    def _update_play_btn_state(self, state):
        return getattr(self, 'controller', None) and self.controller.update_play_btn_state(state)

    def _on_state_changed(self, state):
        return getattr(self, 'controller', None) and self.controller.on_state_changed(state)

    def _on_timer(self):
        return getattr(self, 'controller', None) and self.controller.on_timer()

    def _update_lyrics(self, pos):
        return getattr(self, 'controller', None) and self.controller.update_lyrics(pos)

    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "添加歌曲", "", "Audio (*.mp3 *.m4a *.wav *.flac)"
        )
        if files:
            added = self.playlist_manager.add_files(files)
            if added > 0:
                self.playlist_files = self.playlist_manager.files
                self._refresh_playlist_view()
                if self._current_index == -1 and self.playlist_files:
                    self._play_index(0)

    def _format_playlist_item(self, idx: int, path: str) -> str:
        meta = AudioMetadata.from_file(path)
        return f"{idx + 1}. {meta.display_name}"

    def _refresh_playlist_view(self):
        current_row = self.list_widget.currentRow()
        self.list_widget.clear()
        for idx, path in enumerate(self.playlist_manager.files):
            self.list_widget.addItem(self._format_playlist_item(idx, path))
        if self.list_widget.count() > 0:
            row = self._current_index if self._current_index >= 0 else current_row
            row = max(0, min(row, self.list_widget.count() - 1))
            self.list_widget.setCurrentRow(row)

    def _remove_selected_file(self):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self.playlist_manager.files):
            return
        removed = self.playlist_manager.remove_file(row)
        if not removed:
            return
        self.playlist_files = self.playlist_manager.files
        self._refresh_playlist_view()

        if row == self._current_index:
            if self._remove_behavior == "next" and self.playlist_manager.has_files():
                self._current_index = -1
                next_idx = min(row, len(self.playlist_manager.files) - 1)
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
        # PlaylistManager 已自动持久化

    def _move_selected_up(self):
        row = self.list_widget.currentRow()
        if row <= 0 or row >= len(self.playlist_manager.files):
            return
        moved = self.playlist_manager.move_file_up(row)
        if not moved:
            return
        self.playlist_files = self.playlist_manager.files
        self._refresh_playlist_view()
        self.list_widget.setCurrentRow(row - 1)
        self._current_index = self.playlist_manager.current_index

    def _move_selected_down(self):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self.playlist_manager.files) - 1:
            return
        moved = self.playlist_manager.move_file_down(row)
        if not moved:
            return
        self.playlist_files = self.playlist_manager.files
        self._refresh_playlist_view()
        self.list_widget.setCurrentRow(row + 1)
        self._current_index = self.playlist_manager.current_index
    

    # 使用 app_state.save_state/load_state 进行状态持久化

    def _save_playlist_to_disk(self):
        # 委托给 PlaylistManager 持久化
        try:
            self.playlist_manager.save_to_disk()
        except Exception as exc:
            logger.error("Saving playlist failed: %s", exc)

    def _load_playlist_from_disk(self):
        # PlaylistManager 在初始化时已加载磁盘数据，刷新视图
        self.playlist_files = self.playlist_manager.files
        self._refresh_playlist_view()
        self._current_index = self.playlist_manager.current_index

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
            # 使用 PlaylistManager 中的原子写入实现以避免重复代码
            if hasattr(self, 'playlist_manager') and hasattr(self.playlist_manager, '_atomic_write_text'):
                self.playlist_manager._atomic_write_text(
                    self._state_store,
                    json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                )
            else:
                # 回退到简单写入
                self._state_store.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
            self.lbl_title.setText("飞羽播放器")
        elif mode == 1:  # 播放列表
            self.content_stack.setCurrentIndex(1)
            self.button_stack.setCurrentIndex(1)
            self.lbl_title.setText("播放列表")
        # Mode 2 (hidden) is no longer used

    def _play_index(self, idx, autoplay: bool = True, start_pos_ms: int = 0):
        return getattr(self, 'controller', None) and self.controller.play_index(idx, autoplay, start_pos_ms)

    def _prev(self):
        return getattr(self, 'controller', None) and self.controller.prev()

    def _next(self):
        return getattr(self, 'controller', None) and self.controller.next()

    def _on_position_changed(self, ms):
        return getattr(self, 'controller', None) and self.controller.on_position_changed(ms)

    def _on_duration_changed(self, ms):
        return getattr(self, 'controller', None) and self.controller.on_duration_changed(ms)

    def _on_item_dbl_click(self, item):
        return getattr(self, 'controller', None) and self.controller.on_item_double_click(item)

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