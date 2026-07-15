"""Trigger-context linter.

Two checks born from real bugs:

1. Effects inside trigger contexts. Scripted-GUI `triggers = {}` / `visible = {}`
   blocks and everything in common/scripted_triggers are trigger contexts: the
   engine silently ignores (or misbehaves on) effect statements there. Temp-variable
   math (set_temp_variable etc.) is tolerated - the codebase relies on it - but
   persistent-state effects and loop effects are flagged.

2. Unguarded division. `divide_[temp_]variable` by a dynamic variable that can be
   0/unset spams "Trying to divide by zero" every frame when it's in a GUI context.
   Flagged unless a nearby preceding line checks the divisor.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..core import config, pdx

# definite effects that must never appear in a trigger context
_EFFECT_KEYWORDS = (
    "set_variable", "add_to_variable", "subtract_from_variable",
    "multiply_variable", "divide_variable", "round_variable", "clamp_variable",
    "clear_variable", "add_to_array", "remove_from_array", "clear_array",
    "resize_array", "for_each_loop", "for_each_scope_loop", "for_loop_effect",
    "while_loop_effect", "random_list", "country_event", "news_event",
    "set_country_flag", "clr_country_flag", "set_global_flag", "clr_global_flag",
    "add_political_power", "add_command_power", "meta_effect",
)
_EFFECT_RE = re.compile(r"^\s*(" + "|".join(_EFFECT_KEYWORDS) + r")\s*=")

# both forms: `divide_x = { name = divisor }` and `divide_x = { var = name value = divisor }`
_DIVIDE_RE = re.compile(
    r"\b(divide_variable|divide_temp_variable)\s*=\s*\{\s*(?:var\s*=\s*)?"
    r"[A-Za-z0-9_.@:^]+\s*=?\s*(?:value\s*=\s*)?([A-Za-z0-9_.@:^]+)"
)
_NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?$")

# scripted-GUI block headers that open a trigger context
_TRIGGER_BLOCK_HEADERS = re.compile(r"^\s*(triggers|visible)\s*=\s*\{")


def _strip_comment(line: str) -> str:
    i = line.find("#")
    return line if i < 0 else line[:i]


def _trigger_context_lines(text: str, whole_file_is_trigger: bool) -> set[int]:
    """Line numbers (1-based) that sit inside a trigger context."""
    if whole_file_is_trigger:
        return set(range(1, text.count("\n") + 2))
    inside: set[int] = set()
    depth_stack: list[int] = []  # brace depths at which a trigger block opened
    depth = 0
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = _strip_comment(raw)
        opened_here = bool(_TRIGGER_BLOCK_HEADERS.match(line))
        if opened_here:
            depth_stack.append(depth)
        if depth_stack:
            inside.add(lineno)
        depth += line.count("{") - line.count("}")
        while depth_stack and depth <= depth_stack[-1]:
            depth_stack.pop()
    return inside


def _check_file(path: Path, root: Path, whole_file_is_trigger: bool) -> list[str]:
    try:
        text = pdx.read_text(path)
    except OSError:
        return []
    rel = str(path.relative_to(root))
    lines = text.splitlines()
    trigger_lines = _trigger_context_lines(text, whole_file_is_trigger)
    findings: list[str] = []

    for lineno, raw in enumerate(lines, 1):
        line = _strip_comment(raw)
        if not line.strip():
            continue

        if lineno in trigger_lines:
            m = _EFFECT_RE.match(line)
            if m:
                findings.append(
                    f"{rel}:{lineno}: effect '{m.group(1)}' inside a trigger context"
                    " (engine ignores or misbehaves; restructure or move to effects)"
                )

        for m in _DIVIDE_RE.finditer(line):
            divisor = m.group(2)
            if _NUMBER_RE.match(divisor):
                continue
            base = divisor.split("@", 1)[0].split("^", 1)[0].split(":")[-1]
            guarded = False
            for back in lines[max(0, lineno - 16):lineno - 1]:
                if base in back and re.search(r"check_variable|has_variable", back):
                    guarded = True
                    break
            if not guarded:
                findings.append(
                    f"{rel}:{lineno}: {m.group(1)} by dynamic '{divisor}' with no"
                    " nearby guard - divide-by-zero log spam if it can be 0/unset"
                )
    return findings


def lint(file: str | None = None) -> str:
    """Lint trigger contexts across scripted_guis + scripted_triggers (or one file)."""
    root = config.mod_path()
    targets: list[tuple[Path, bool]] = []
    if file:
        p = root / file
        if not p.exists():
            return f"File not found: {file}"
        targets.append((p, "scripted_triggers" in p.parts))
    else:
        for f in sorted((root / "common" / "scripted_guis").glob("*.txt")):
            targets.append((f, False))
        st = root / "common" / "scripted_triggers"
        if st.is_dir():
            for f in sorted(st.glob("*.txt")):
                targets.append((f, True))

    findings: list[str] = []
    for path, whole in targets:
        findings.extend(_check_file(path, root, whole))

    if not findings:
        return f"Checked {len(targets)} file(s): no trigger-context violations found."
    return (
        f"Checked {len(targets)} file(s): {len(findings)} finding(s).\n"
        + "\n".join(findings)
    )
