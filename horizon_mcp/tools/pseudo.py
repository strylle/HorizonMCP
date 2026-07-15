"""Pseudodecision integrity checker.

A pseudodecision is a contract spread across six files; any missing leg fails
silently in-game (a click that activates a nonexistent decision, an empty-suffix
meta_effect, a nameless card). For every pseudodecision registered via
OTH_init_proxy_pseudodecision this verifies:

  1. its token is in synchronized_dynamic_tokens/tokens.txt
  2. every registered effect token e has a scripted effect <token>_<e>
  3. every registered trigger token t has a scripted trigger <token>_<t>
  4. a backing decision <token> exists in common/decisions
  5. its dummy mission <token>_timeout exists (mission-type pseudodecisions
     with mission_days_timeout are exempt - they never activate the dummy)
  6. loc keys <token> and <token>_desc exist
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..core import config, pdx

_REGISTER_RE = re.compile(
    r"set_temp_variable\s*=\s*\{\s*pseudodecision\s*=\s*token:([A-Za-z0-9_]+)\s*\}"
)
_EFFECT_TOKEN_RE = re.compile(r"\{\s*effects\s*=\s*token:([A-Za-z0-9_]+)\s*\}")
_TRIGGER_TOKEN_RE = re.compile(r"\{\s*triggers\s*=\s*token:([A-Za-z0-9_]+)\s*\}")
_MISSION_TIMEOUT_RE = re.compile(r"\{\s*mission_days_timeout\s*=\s*(\d+)")
_INIT_CALL = "OTH_init_proxy_pseudodecision"
_TOP_DEF_RE_TMPL = r"^\s*{name}\s*=\s*\{{"


@dataclass
class Registration:
    token: str
    file: str
    line: int
    effects: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    mission: bool = False


def _find_registrations(root: Path) -> list[Registration]:
    regs: list[Registration] = []
    for path in sorted((root / "common" / "ideas").glob("*.txt")):
        try:
            text = pdx.read_text(path)
        except OSError:
            continue
        rel = str(path.relative_to(root))
        lines = text.splitlines()
        current: Registration | None = None
        for lineno, raw in enumerate(lines, 1):
            line = raw.split("#", 1)[0]
            m = _REGISTER_RE.search(line)
            if m:
                # a new registration opens; the previous one (if unclosed) was abandoned
                current = Registration(token=m.group(1), file=rel, line=lineno)
                continue
            if current is None:
                continue
            current.effects += _EFFECT_TOKEN_RE.findall(line)
            current.triggers += _TRIGGER_TOKEN_RE.findall(line)
            if _MISSION_TIMEOUT_RE.search(line):
                current.mission = True
            if _INIT_CALL in line:
                regs.append(current)
                current = None
    return regs


def _collect_top_level_defs(directory: Path) -> set[str]:
    """Names defined at any block level `<name> = {` in every .txt under directory."""
    names: set[str] = set()
    if not directory.is_dir():
        return names
    def_re = re.compile(r"^\s*([A-Za-z0-9_]+)\s*=\s*\{", re.MULTILINE)
    for path in sorted(directory.rglob("*.txt")):
        try:
            text = pdx.read_text(path)
        except OSError:
            continue
        for m in def_re.finditer(text):
            names.add(m.group(1))
    return names


def _collect_loc_keys(root: Path) -> set[str]:
    keys: set[str] = set()
    key_re = re.compile(r"^\s+([A-Za-z0-9_.\-]+):\d*\s", re.MULTILINE)
    for path in sorted((root / "localisation").rglob("*_l_english.yml")):
        try:
            text = pdx.read_text(path)
        except OSError:
            continue
        for m in key_re.finditer(text):
            keys.add(m.group(1))
    return keys


def check() -> str:
    root = config.mod_path()
    regs = _find_registrations(root)
    if not regs:
        return "No pseudodecision registrations found in common/ideas."

    tokens_file = config.synchronized_tokens_file()
    known_tokens = set(
        pdx.read_text(tokens_file).splitlines()
    ) if tokens_file.exists() else set()
    effect_defs = _collect_top_level_defs(root / "common" / "scripted_effects")
    trigger_defs = _collect_top_level_defs(root / "common" / "scripted_triggers")
    decision_defs = _collect_top_level_defs(root / "common" / "decisions")
    loc_keys = _collect_loc_keys(root)

    lines: list[str] = []
    total_problems = 0
    for reg in regs:
        problems: list[str] = []
        if reg.token not in known_tokens:
            problems.append("token missing from synchronized_dynamic_tokens/tokens.txt")
        for e in reg.effects:
            name = f"{reg.token}_{e}"
            if name not in effect_defs:
                problems.append(f"missing scripted effect '{name}' (payload)")
        for t in reg.triggers:
            name = f"{reg.token}_{t}"
            if name not in trigger_defs:
                problems.append(f"missing scripted trigger '{name}' (meta-trigger body)")
        if reg.token not in decision_defs:
            problems.append("missing backing decision (btn_select_click activates a nonexistent decision)")
        if not reg.mission and f"{reg.token}_timeout" not in decision_defs:
            problems.append(f"missing dummy mission '{reg.token}_timeout'")
        if reg.token not in loc_keys:
            problems.append("missing loc key (card shows raw token)")
        if f"{reg.token}_desc" not in loc_keys:
            problems.append(f"missing loc key '{reg.token}_desc'")

        kind = "mission" if reg.mission else "decision"
        if problems:
            total_problems += len(problems)
            lines.append(f"FAIL {reg.token} ({kind}, registered {reg.file}:{reg.line}):")
            lines.extend(f"    - {p}" for p in problems)
        else:
            lines.append(f"OK   {reg.token} ({kind})")

    header = (
        f"Checked {len(regs)} pseudodecision registration(s): "
        + (f"{total_problems} problem(s)." if total_problems else "all contracts intact.")
    )
    return header + "\n" + "\n".join(lines)
