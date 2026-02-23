"""
app_controller.py - 应用控制器

将播放器、播放列表、歌词组件与主窗口的信号/事件绑定集中管理，便于解耦与测试。
"""
from __future__ import annotations

from typing import Any
import os

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QPixmap
from component_metadata import AudioMetadata
from component_lyrics_parser import LrcParser


class AppController:
    def __init__(self, main_window: Any):
        self.main = main_window
        self._bind_signals()

    def _bind_signals(self):
        m = self.main
        # Playlist UI
        try:
            m.list_widget.customContextMenuRequested.connect(m._show_playlist_context_menu)
        except Exception:
            pass
        try:
            m.list_widget.itemDoubleClicked.connect(self.on_item_double_click)
        except Exception:
            pass

        # Slider controls (progress)
        try:
            m.slider.sliderPressed.connect(m._player.pause)
            m.slider.sliderReleased.connect(m._player.play)
            m.slider.sliderMoved.connect(lambda v: m._player.setPosition(v * 1000))
        except Exception:
            pass

        # Player signals
        try:
            m._player.positionChanged.connect(self.on_position_changed)
            m._player.durationChanged.connect(self.on_duration_changed)
            m._player.playbackStateChanged.connect(self.on_state_changed)
            # Keep metadata handling in MainPlayer (uses UI-specific logic)
            m._player.metaDataChanged.connect(m._on_metadata_changed)
        except Exception:
            pass

    # Player event handlers moved from MainPlayer
    def toggle_play(self):
        if self.main._player.playbackState() == self.main._player.PlaybackState.PlayingState:
            self.main._player.pause()
        else:
            self.main._player.play()

    def update_play_btn_state(self, state):
        if state == self.main._player.PlaybackState.PlayingState:
            if hasattr(self.main, "_play_toggle_layout"):
                self.main._play_toggle_layout.setCurrentWidget(self.main.btn_pause)
        else:
            if hasattr(self.main, "_play_toggle_layout"):
                self.main._play_toggle_layout.setCurrentWidget(self.main.btn_play)

    def on_state_changed(self, state):
        self.update_play_btn_state(state)

        if state == self.main._player.PlaybackState.PlayingState:
            if hasattr(self.main, 'vinyl'):
                self.main.vinyl.start_anim()
            if hasattr(self.main, "spectrum_widget"):
                self.main.spectrum_widget.set_active(True)
            if hasattr(self.main, "_timer"):
                self.main._timer.start()
        elif state == self.main._player.PlaybackState.PausedState:
            if hasattr(self.main, 'vinyl'):
                self.main.vinyl.pause_anim()
            if hasattr(self.main, "spectrum_widget"):
                self.main.spectrum_widget.set_active(False)
        else:
            if hasattr(self.main, 'vinyl'):
                self.main.vinyl.stop_anim()
            if hasattr(self.main, "spectrum_widget"):
                self.main.spectrum_widget.set_active(False)

    def on_timer(self):
        if self.main._player.playbackState() == self.main._player.PlaybackState.PlayingState:
            self.update_lyrics(self.main._player.position())

    def update_lyrics(self, pos):
        if not hasattr(self.main, "_current_lrc") or not self.main._current_lrc:
            return
        if not self.main._current_lrc.lyrics:
            return
        if self.main._lyrics_lock_line:
            return
        current_idx = self.main._current_lrc.get_current_index(pos + self.main._lyrics_offset_ms)
        if current_idx < 0:
            current_idx = 0
        if current_idx == self.main._last_lyric_index:
            return
        self.main._last_lyric_index = current_idx
        if hasattr(self.main, 'lyrics_display'):
            self.main.lyrics_display.set_current_index(current_idx, animate=True)

    def on_position_changed(self, ms):
        self.main._resume_position_ms = int(ms)
        try:
            if not self.main.slider.isSliderDown():
                self.main.slider.setValue(ms // 1000)
        except Exception:
            pass
        try:
            self.main.lbl_curr.setText(f"{ms // 60000:02d}:{(ms // 1000) % 60:02d}")
        except Exception:
            pass

    def on_duration_changed(self, ms):
        try:
            self.main.slider.setMaximum(ms // 1000)
        except Exception:
            pass
        try:
            self.main.lbl_total.setText(f"{ms // 60000:02d}:{(ms // 1000) % 60:02d}")
        except Exception:
            pass

    def play_index(self, idx, autoplay: bool = True, start_pos_ms: int = 0):
        pm = self.main.playlist_manager
        if not (0 <= idx < len(pm.files)):
            return
        self.main._current_index = idx
        try:
            self.main.list_widget.setCurrentRow(idx)
        except Exception:
            pass
        path = pm.get_file(idx)
        if not path:
            return
        try:
            self.main._player.setSource(QUrl.fromLocalFile(path))
        except Exception:
            pass

        if autoplay:
            self.main._player.play()
            if hasattr(self.main, '_timer'):
                self.main._timer.start()
        else:
            self.main._player.pause()
            if hasattr(self.main, '_timer'):
                self.main._timer.stop()
            if start_pos_ms > 0:
                try:
                    self.main._player.setPosition(start_pos_ms)
                except Exception:
                    pass

        # Update Meta
        try:
            meta = AudioMetadata.from_file(path)
            self.main.lbl_info.setText(meta.display_name)
            self.main._update_info_bar_from_path(path)
        except Exception:
            pass

        # Cover
        try:
            if meta.cover_data:
                pm_pix = QPixmap()
                pm_pix.loadFromData(meta.cover_data)
                self.main.vinyl.set_cover(pm_pix)
                self.main._set_adaptive_background(pm_pix, animate=True)
            else:
                self.main.vinyl.set_cover(None)
                self.main._set_adaptive_background(None, animate=False)
        except Exception:
            pass

        # Lyrics
        self.main._current_lrc = None
        try:
            lrc_path = os.path.splitext(path)[0] + ".lrc"
            if os.path.exists(lrc_path):
                self.main._current_lrc = LrcParser(lrc_path)
            elif meta.lyrics_text:
                self.main._current_lrc = LrcParser(meta.lyrics_text, is_text=True)
        except Exception:
            pass

        if not self.main._current_lrc:
            self.main._set_lyrics_status("暂无歌词")
        else:
            self.main._load_lyrics_to_embedded_display()
            self.update_lyrics(0)

        pm.set_current_index(idx)
        try:
            self.main._save_playlist_to_disk()
        except Exception:
            pass

    def prev(self):
        if self.main._current_index > 0:
            self.play_index(self.main._current_index - 1)

    def next(self):
        if self.main._current_index < len(self.main.playlist_manager.files) - 1:
            self.play_index(self.main._current_index + 1)

    def on_item_double_click(self, item):
        try:
            idx = self.main.list_widget.row(item)
            self.play_index(idx)
        except Exception:
            pass
