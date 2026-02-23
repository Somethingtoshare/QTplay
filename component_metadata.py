"""
metadata.py - 音频元数据解析
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
logger = logging.getLogger(__name__)

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