"""Check that every GFX_ sprite a file references is actually defined somewhere.

Handles the bracket-substituted names CWTools is blind to, e.g.
GFX_proxy_briefing_intelligence_agency_icon_[ROOT.GetTag] - we can't know
every tag the game will substitute, but we CAN tell you whether *any* sprite
with that prefix exists, and list which variants do.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..core import config, pdx

# a sprite definition: name = "GFX_whatever" (quotes optional)
_SPRITE_DEF_RE = re.compile(r'\bname\s*=\s*"?(GFX_[A-Za-z0-9_\-\.]+)"?')

# a sprite reference in a .gui / script file, possibly with [bracket] substitutions
# e.g. GFX_foo, GFX_foo_[ROOT.GetTag], GFX_foo_[?briefing.GetTokenKey]_bar
_SPRITE_REF_RE = re.compile(
    r"GFX_[A-Za-z0-9_\-\.]*(?:\[[^\]\r\n]+\][A-Za-z0-9_\-\.]*)*"
)


def _iter_gfx_files() -> list[Path]:
    files = list(config.mod_path().rglob("*.gfx"))
    game = config.game_path()
    if game is not None:
        files.extend((game / "interface").rglob("*.gfx"))
    return files


def index_defined_sprites() -> set[str]:
    """Every sprite name defined in the mod's .gfx files plus vanilla's (if GAME_PATH resolves)."""
    defined: set[str] = set()
    for f in _iter_gfx_files():
        try:
            text = pdx.read_text(f)
        except (OSError, UnicodeDecodeError):
            continue
        defined.update(_SPRITE_DEF_RE.findall(text))
    return defined


def extract_references(text: str) -> list[str]:
    """Every distinct GFX_ reference in a block of text, first-seen order."""
    found: list[str] = []
    for match in _SPRITE_REF_RE.finditer(text):
        ref = match.group(0).rstrip("_.")
        if ref not in found:
            found.append(ref)
    return found


def check_file(rel_path: str) -> str:
    """Check every sprite referenced by one file against all defined sprites."""
    path = config.mod_path() / rel_path
    if not path.exists():
        raise FileNotFoundError(f"No such file in mod: {rel_path}")
    defined = index_defined_sprites()
    return _report_for(path, pdx.read_text(path), defined)


def check_all() -> str:
    """Check every .gui file and scripted_guis script in the mod."""
    defined = index_defined_sprites()
    targets = sorted(config.mod_path().rglob("*.gui"))
    targets += sorted((config.mod_path() / "common" / "scripted_guis").glob("*.txt"))
    reports = []
    clean = 0
    for path in targets:
        try:
            text = pdx.read_text(path)
        except (OSError, UnicodeDecodeError):
            continue
        report = _report_for(path, text, defined)
        if report.endswith("all sprite references resolve."):
            clean += 1
        else:
            reports.append(report)
    header = (
        f"Checked {len(targets)} file(s) against {len(defined)} defined sprites "
        f"({clean} clean)."
    )
    if not reports:
        return header + " No problems found."
    return header + "\n\n" + "\n\n".join(reports)


def _report_for(path: Path, text: str, defined: set[str]) -> str:
    refs = extract_references(text)
    missing: list[str] = []
    bracket_lines: list[str] = []
    for ref in refs:
        if "[" not in ref:
            if ref == "GFX":  # regex debris from stray 'GFX_' fragments
                continue
            if ref not in defined:
                missing.append(ref)
            continue
        # bracket-substituted: check the static prefix has at least one real variant
        prefix = ref.split("[", 1)[0]
        if prefix == "GFX_":
            # the whole name is dynamic - matching every sprite proves nothing
            bracket_lines.append(f"  {ref}  ->  prefix too generic to check statically")
            continue
        variants = sorted(s for s in defined if s.startswith(prefix))
        if not variants:
            bracket_lines.append(f"  {ref}  ->  NO sprite starts with '{prefix}'")
        else:
            sample = ", ".join(variants[:5])
            more = f" (+{len(variants) - 5} more)" if len(variants) > 5 else ""
            bracket_lines.append(f"  {ref}  ->  {len(variants)} variant(s): {sample}{more}")

    rel = path.name if config.mod_path() not in path.parents else str(
        path.relative_to(config.mod_path())
    )
    lines = [f"{rel}: {len(refs)} sprite reference(s)."]
    if missing:
        lines.append(f" Missing ({len(missing)}):")
        lines.extend(f"  {m}" for m in missing)
    if bracket_lines:
        lines.append(" Bracket-substituted (verify the variants you need exist):")
        lines.extend(bracket_lines)
    if not missing and not bracket_lines:
        lines[-1] += " all sprite references resolve."
    return "\n".join(lines)
