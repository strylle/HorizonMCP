"""I/O helpers! LOG_PATH MUST be defined for this to work. Otherwise the program won't work!
"""

from __future__ import annotations

import os
from pathlib import Path


def mod_path() -> Path:
    """Reads MOD_PATH"""
    raw = os.environ.get("MOD_PATH")
    if not raw:
        raise FileNotFoundError(
            "MOD_PATH environment variable not set. "
        )
    path = Path(raw).expanduser()
    if not path.is_dir():
        raise FileNotFoundError(
            f"MOD_PATH points to a non-existent folder: {path}"
        )
    return path


def events_dir() -> Path:
    return mod_path() / "events"


def loc_dir() -> Path:
    return mod_path() / "localisation" / "english"


def synchronized_tokens_file() -> Path:
    return mod_path() / "common" / "synchronized_dynamic_tokens" / "tokens.txt"


def game_path() -> Path | None:
    """Reads GAME_PATH (the HOI4 install, for vanilla sprite lookups).

    Falls back to the default macOS Steam location; returns None if neither exists,
    in which case vanilla assets just aren't indexed.
    """
    raw = os.environ.get("GAME_PATH")
    if raw:
        path = Path(raw).expanduser()
        return path if path.is_dir() else None
    default = Path(
        "~/Library/Application Support/Steam/steamapps/common/Hearts of Iron IV"
    ).expanduser()
    return default if default.is_dir() else None


def log_file(override: str | None = None) -> Path:
    """Reads the HOI4 error log. Is the same on Windows & MacOS (srry idk about linux)
    """
    if override:
        return Path(override).expanduser()
    raw = os.environ.get("LOG_PATH")
    if raw:
        return Path(raw).expanduser()
    return Path(
        "~/Documents/Paradox Interactive/Hearts of Iron IV/logs/error.log"
    ).expanduser()
