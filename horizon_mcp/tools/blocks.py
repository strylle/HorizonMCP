"""Mechanical Paradox-script surgery: validate brace balance, remove named blocks.

Every rip-out session ends up hand-rolling the same brace-walking python;
this bakes it in so deletions can't silently unbalance a file.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..core import config, pdx

# gui style:    name = "some_window"      (inside a block header's body)
# script style: some_effect = {           (the block header itself)
_GUI_NAME_RE_TMPL = r'\bname\s*=\s*"?{}"?\s*$'
_SCRIPT_HEADER_RE_TMPL = r"^\s*{}\s*=\s*\{{"


def _strip_comment(line: str) -> str:
    """Drop a # comment so braces inside comments don't skew counts."""
    idx = line.find("#")
    return line if idx == -1 else line[:idx]


def brace_report(text: str) -> tuple[int, int]:
    opens = closes = 0
    for line in text.splitlines():
        line = _strip_comment(line)
        opens += line.count("{")
        closes += line.count("}")
    return opens, closes


def validate_file(rel_path: str) -> str:
    path = config.mod_path() / rel_path
    if not path.exists():
        raise FileNotFoundError(f"No such file in mod: {rel_path}")
    return _validate(path)


def validate_all() -> str:
    """Sweep every script-ish file in the mod for brace imbalance."""
    targets: list[Path] = []
    for pattern in ("common/**/*.txt", "events/*.txt", "interface/**/*.gui", "interface/**/*.gfx"):
        targets.extend(sorted(config.mod_path().glob(pattern)))
    bad = []
    for path in targets:
        report = _validate(path)
        if "OK" not in report:
            bad.append(report)
    if not bad:
        return f"Checked {len(targets)} file(s): all balanced."
    return f"Checked {len(targets)} file(s), {len(bad)} problem(s):\n" + "\n".join(bad)


def _validate(path: Path) -> str:
    rel = path.relative_to(config.mod_path())
    try:
        text = pdx.read_text(path)
    except (OSError, UnicodeDecodeError) as exc:
        return f"{rel}: UNREADABLE ({exc})"
    opens, closes = brace_report(text)
    if opens != closes:
        return f"{rel}: UNBALANCED - {opens} open vs {closes} close ({opens - closes:+d})"
    return f"{rel}: OK ({opens} braces)"


def remove_block(rel_path: str, name: str, dry_run: bool = False) -> str:
    """Remove a named block (gui element or script definition) from a file.

    Matches either a `name = "<name>"` line (gui style; removes the enclosing
    block) or a `<name> = {` header (script style). Refuses ambiguous matches.
    """
    path = config.mod_path() / rel_path
    if not path.exists():
        raise FileNotFoundError(f"No such file in mod: {rel_path}")
    text = pdx.read_text(path)
    lines = text.splitlines(keepends=True)

    gui_re = re.compile(_GUI_NAME_RE_TMPL.format(re.escape(name)))
    script_re = re.compile(_SCRIPT_HEADER_RE_TMPL.format(re.escape(name)))

    starts: list[int] = []
    for i, line in enumerate(lines):
        stripped = _strip_comment(line).rstrip()
        if script_re.match(stripped):
            starts.append(i)
        elif gui_re.search(stripped):
            # walk back to the enclosing block's opening line
            j = i
            depth = 0
            while j >= 0:
                cleaned = _strip_comment(lines[j])
                depth += cleaned.count("}") - cleaned.count("{")
                if depth < 0:
                    starts.append(j)
                    break
                j -= 1

    starts = sorted(set(starts))
    if not starts:
        return f"No block named '{name}' found in {rel_path}."
    if len(starts) > 1:
        locs = ", ".join(f"line {s + 1}" for s in starts)
        return (
            f"Ambiguous: '{name}' matches {len(starts)} blocks in {rel_path} ({locs}). "
            "Not removing anything - disambiguate by hand."
        )

    start = starts[0]
    depth = 0
    end = None
    for j in range(start, len(lines)):
        cleaned = _strip_comment(lines[j])
        depth += cleaned.count("{") - cleaned.count("}")
        if depth == 0:
            end = j
            break
    if end is None:
        return f"Block '{name}' at line {start + 1} never closes - file is unbalanced, fix that first."

    removed = end - start + 1
    new_text = "".join(lines[:start] + lines[end + 1:])
    opens, closes = brace_report(new_text)
    verdict = "balanced" if opens == closes else f"UNBALANCED ({opens} vs {closes})"

    if dry_run:
        preview = "".join(lines[start:min(start + 5, end + 1)])
        return (
            f"[dry run] Would remove '{name}': lines {start + 1}-{end + 1} "
            f"({removed} lines) from {rel_path}; result would be {verdict}.\n"
            f"Block starts:\n{preview}"
        )

    path.write_text(new_text, encoding="utf-8")
    return (
        f"Removed '{name}': lines {start + 1}-{end + 1} ({removed} lines) "
        f"from {rel_path}. File is now {verdict}."
    )
