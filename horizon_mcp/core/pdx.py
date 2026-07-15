"""More I/O helpers! Specifically for reading and writing to files.

Localisation files are UTF-8 *with BOM*. Anything else is just UTF-8 (e.g .gui, .txt, .gfx).
"""

from __future__ import annotations

import re
from pathlib import Path

from . import config

# `add_namespace = usa_flavor`  (optionally quoted)
_NAMESPACE_RE = re.compile(r'add_namespace\s*=\s*"?([A-Za-z0-9_]+)"?')


def read_text(path: Path) -> str:
    """Reads a file, stripping a BOM if it has one, so callers don't care which file type they're loading"""
    return path.read_text(encoding="utf-8-sig") # localization files are UTF-8 w/ bom


def index_event_namespaces() -> dict[str, Path]:
    """Builds an index of event namespaces, so looking up which file owns one is a single lookup instead of a rescan"""
    mapping: dict[str, Path] = {}
    for f in sorted(config.events_dir().glob("*.txt")):
        try:
            text = read_text(f)
        except OSError:
            continue
        for ns in _NAMESPACE_RE.findall(text):
            mapping.setdefault(ns, f)
    return mapping


def find_next_event_id(event_file: Path, namespace: str) -> int:
    """Finds the next free event id for a namespace, so new events never collide with an existing one"""
    text = read_text(event_file)
    pattern = re.compile(rf"\bid\s*=\s*{re.escape(namespace)}\.(\d+)")
    used = [int(m) for m in pattern.findall(text)]
    return max(used) + 1 if used else 1


def find_loc_file_for_namespace(namespace: str) -> Path | None:
    """Finds the loc file that already owns a namespace, to not make new files for every single new localization line"""
    key_prefix = re.compile(rf"^\s*{re.escape(namespace)}\.\d+\.", re.MULTILINE)
    for f in sorted(config.loc_dir().glob("*_l_english.yml")):
        try:
            text = read_text(f)
        except OSError:
            continue
        if key_prefix.search(text):
            return f
    return None


def append_script_block(path: Path, block: str) -> None:
    """Appends a script block to a .txt file, spacing it correctly from whatever's already there"""
    existing = read_text(path) if path.exists() else ""
    sep = "" if existing.endswith("\n\n") or existing == "" else (
        "\n" if existing.endswith("\n") else "\n\n"
    )
    path.write_text(existing + sep + block.rstrip() + "\n", encoding="utf-8")


def append_loc_entries(path: Path, entries: list[tuple[str, str]]) -> None:
    """Appends loc entries under the l_english: header, creating the file if it's new"""
    if path.exists():
        text = read_text(path)
    else:
        text = "l_english:\n"
    lines = [text.rstrip("\n")]
    for key, value in entries:
        safe = value.replace('"', '\\"')
        lines.append(f' {key}:0 "{safe}"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")


def insert_namespace_declaration(event_file: Path, namespace: str) -> bool:
    """Adds an add_namespace declaration to a file if missing, since every event file needs one before its events will load"""
    text = read_text(event_file) if event_file.exists() else ""
    if namespace in _NAMESPACE_RE.findall(text):
        return False
    decl = f"add_namespace = {namespace}\n"
    matches = list(_NAMESPACE_RE.finditer(text))
    if matches:
        insert_at = text.rfind("\n", 0, matches[-1].end()) + 1
        line_end = text.find("\n", matches[-1].end())
        line_end = line_end + 1 if line_end != -1 else len(text)
        new_text = text[:line_end] + decl + text[line_end:]
    else:
        new_text = decl + text
    event_file.write_text(new_text, encoding="utf-8")
    return True
