"""
app_state.py - 应用状态持久化工具

提供原子写入和 JSON 状态的读写辅助函数，供 `MainPlayer` 使用。
"""
from __future__ import annotations

import json
import tempfile
import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def atomic_write_text(path: Path, content: str) -> None:
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


def save_state(path: Path, state: dict) -> None:
    try:
        atomic_write_text(path, json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    except (OSError, ValueError, TypeError) as exc:
        logger.error("Saving app state failed: %s", exc)


def load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        logger.error("Loading app state failed: %s", exc)
        return {}
