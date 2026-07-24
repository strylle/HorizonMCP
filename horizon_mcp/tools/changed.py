"""Dispatch existing per-file checks against only files changed in the working tree.

Avoids full-mod sweeps (noisy, expensive) for the common case of "did I break
anything I just touched". Deliberately excludes cross-file checks
(check_variable_flow, check_pseudodecisions) - those need whole-mod scope to
be correct, since a write in one file can be read in another outside the diff.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..core import config
from . import blocks, gfx, lint, tokens


def _git_changed_files(against: str) -> list[str]:
    root = config.mod_path()
    diff = subprocess.run(
        ["git", "-C", str(root), "diff", "--name-only", "--diff-filter=d", against],
        capture_output=True, text=True,
    )
    tracked = diff.stdout.splitlines() if diff.returncode == 0 else []
    status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
        capture_output=True, text=True,
    )
    untracked = [
        line[3:] for line in status.stdout.splitlines() if line.startswith("??")
    ]
    seen: list[str] = []
    for f in tracked + untracked:
        if f not in seen:
            seen.append(f)
    return seen


def check(against: str = "HEAD") -> str:
    """Run brace/gfx-ref/trigger-context/tokens-append checks on changed files only."""
    root = config.mod_path()
    files = _git_changed_files(against)
    relevant = [f for f in files if f.endswith((".txt", ".gui", ".gfx"))]
    if not relevant:
        return f"No changed .txt/.gui/.gfx files vs {against}."

    findings: list[str] = []
    tokens_rel = str(config.synchronized_tokens_file().relative_to(root))

    for rel in relevant:
        path = root / rel
        if not path.exists():
            continue
        parts = Path(rel).parts

        if rel == tokens_rel:
            report = tokens.verify_append_only()
            if "DANGER" in report:
                findings.append(report)
            continue

        report = blocks.validate_file(rel)
        if ": OK (" not in report:
            findings.append(report)

        is_gui_ish = rel.endswith(".gui") or (
            rel.endswith(".txt") and "scripted_guis" in parts
        )
        if is_gui_ish:
            report = gfx.check_file(rel)
            if not report.rstrip().endswith("all sprite references resolve."):
                findings.append(report)

        if rel.endswith(".txt") and ("scripted_guis" in parts or "scripted_triggers" in parts):
            report = lint.lint(rel)
            if "no trigger-context violations found" not in report:
                findings.append(report)

    header = f"Checked {len(relevant)} changed file(s) vs {against}."
    if not findings:
        return header + " All clean."
    return header + f" {len(findings)} finding group(s):\n\n" + "\n\n".join(findings)
