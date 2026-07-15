"""Cross-reference dynamic variable/array writes against reads.

Finds write-only variables (dead data: computed but never consumed, like the old
intelligence@ seeds or SAT_PROXY_SUPPORT) and read-only variables (systems running
on data nothing feeds, like the old assigned_operatives@ tick).

Purely lexical: names are normalized to their base identifier (scope prefixes,
@-targets and ^-indexing stripped), temp and persistent variables share one
namespace since reads are indistinguishable.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from ..core import config, pdx

# effects that create/feed a variable or array
_WRITE_KEYS = (
    "set_variable", "set_temp_variable",
    "add_to_variable", "add_to_temp_variable",
    "subtract_from_variable", "subtract_from_temp_variable",
    "add_to_array", "add_to_temp_array",
)
# `set_variable = { NAME = ... }` / `add_to_array = { NAME = ... }`
_WRITE_BLOCK_RE = re.compile(
    r"\b(" + "|".join(_WRITE_KEYS) + r")\s*=\s*\{\s*(?:var\s*=\s*)?([A-Za-z0-9_.@:^]+)"
)
# `check_variable = { NAME ...` / `has_variable = NAME` / `is_in_array = { NAME`
_READ_BLOCK_RE = re.compile(
    r"\b(check_variable|has_variable|is_in_array|clamp_variable|clamp_temp_variable|"
    r"multiply_variable|multiply_temp_variable|divide_variable|divide_temp_variable|"
    r"round_variable|round_temp_variable)\s*=\s*\{?\s*(?:var\s*=\s*)?([A-Za-z0-9_.@:^]+)"
)
# `array = NAME` inside loops, `var:NAME` scope/value refs, `[?NAME]` loc reads
_ARRAY_RE = re.compile(r"\barray\s*=\s*([A-Za-z0-9_.@:^]+)")
_VARREF_RE = re.compile(r"@?var:([A-Za-z0-9_.]+)")
_LOCREF_RE = re.compile(r"\[\?([A-Za-z0-9_.@:^]+?)(?:\|[^\]]*)?\]")
# RHS of a write is a read of whatever appears there
_RHS_RE = re.compile(r"=\s*\{\s*(?:var\s*=\s*)?[A-Za-z0-9_.@:^]+\s+(?:value\s*=\s*)?([A-Za-z0-9_.@:^]+)")
# any `key = <dynamic var>` where the value is unmistakably a variable reference
# (contains @ or var: or global.) - catches reads like `days = X@var:y` in events
_DYN_RHS_RE = re.compile(r"=\s*((?:global\.)?[A-Za-z0-9_.]+@[A-Za-z0-9_.:^]+|var:[A-Za-z0-9_.@:^]+|global\.[A-Za-z0-9_.@:^]+)")

_SCOPE_PREFIX_RE = re.compile(r"^(?:global|ROOT|THIS|PREV|FROM|OWNER|CONTROLLER|[A-Z][A-Z0-9]{2})\.")
_NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?$")


def _base_name(raw: str) -> str | None:
    """Reduce a reference to its base identifier, or None if it isn't a variable."""
    name = raw.strip().strip('"')
    # keep peeling scope prefixes (global.x, PREV.x, USA.x, var:v chains)
    while True:
        m = _SCOPE_PREFIX_RE.match(name)
        if m:
            name = name[m.end():]
            continue
        if name.startswith("var:"):
            name = name[4:]
            continue
        break
    name = name.split("@", 1)[0].split("^", 1)[0]
    # loc function calls like [?x.GetFlag] / [?x.GetTokenLocalizedKey] read x
    name = re.sub(r"\.Get[A-Za-z]*$", "", name)
    if not name or _NUMBER_RE.match(name) or name.startswith("token:"):
        return None
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", name):
        return None
    return name


def _scan_dirs() -> list[Path]:
    root = config.mod_path()
    files: list[Path] = []
    for sub in ("common", "events"):
        files.extend(sorted((root / sub).rglob("*.txt")))
    files.extend(sorted((root / "localisation").rglob("*_l_english.yml")))
    return files


def _strip_comment(line: str) -> str:
    i = line.find("#")
    return line if i < 0 else line[:i]


def check_flow(prefix: str | None = None, max_examples: int = 3) -> str:
    """Report write-only and read-only variables, optionally filtered by name prefix."""
    root = config.mod_path()
    writes: dict[str, list[str]] = defaultdict(list)
    reads: dict[str, list[str]] = defaultdict(list)

    for path in _scan_dirs():
        try:
            text = pdx.read_text(path)
        except OSError:
            continue
        rel = str(path.relative_to(root))
        is_loc = path.suffix == ".yml"
        for lineno, raw_line in enumerate(text.splitlines(), 1):
            line = raw_line if is_loc else _strip_comment(raw_line)
            if not line.strip():
                continue
            where = f"{rel}:{lineno}"
            if is_loc:
                for m in _LOCREF_RE.finditer(line):
                    name = _base_name(m.group(1))
                    if name:
                        reads[name].append(where)
                continue
            for m in _WRITE_BLOCK_RE.finditer(line):
                name = _base_name(m.group(2))
                if name:
                    writes[name].append(where)
            for m in _READ_BLOCK_RE.finditer(line):
                name = _base_name(m.group(2))
                if name:
                    reads[name].append(where)
            for regex in (_ARRAY_RE, _VARREF_RE, _LOCREF_RE, _RHS_RE):
                for m in regex.finditer(line):
                    name = _base_name(m.group(1))
                    if name:
                        reads[name].append(where)
            # generic RHS reads only on lines that aren't writes/clears themselves
            # (clear_variable = X destroys X, it doesn't read it; write blocks are
            # already handled by _RHS_RE)
            if "clear_" not in line and not _WRITE_BLOCK_RE.search(line):
                for m in _DYN_RHS_RE.finditer(line):
                    name = _base_name(m.group(1))
                    if name:
                        reads[name].append(where)

    def keep(name: str) -> bool:
        return prefix is None or name.startswith(prefix)

    write_only = sorted(n for n in writes if n not in reads and keep(n))
    read_only = sorted(n for n in reads if n not in writes and keep(n))

    lines: list[str] = []
    scope = f" (prefix '{prefix}')" if prefix else ""
    lines.append(
        f"Variable flow{scope}: {len(writes)} written, {len(reads)} read."
    )
    lines.append(f"\nWRITE-ONLY ({len(write_only)}) - computed but never consumed:")
    for name in write_only:
        locs = ", ".join(writes[name][:max_examples])
        lines.append(f"  {name}  [{len(writes[name])}x: {locs}]")
    if not write_only:
        lines.append("  (none)")
    lines.append(f"\nREAD-ONLY ({len(read_only)}) - consumed but never fed:")
    for name in read_only:
        locs = ", ".join(reads[name][:max_examples])
        lines.append(f"  {name}  [{len(reads[name])}x: {locs}]")
    if not read_only:
        lines.append("  (none)")
    lines.append(
        "\nNote: lexical analysis. Loop value-vars, meta_effect-built names, and"
        " engine-fed values (e.g. mission days_mission_timeout@) can be false positives."
    )
    return "\n".join(lines)
