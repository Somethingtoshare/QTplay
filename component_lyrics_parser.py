"""
lrc_parser.py - 歌词解析器
"""

import os
import re


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