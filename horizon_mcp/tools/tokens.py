"""Fix "dynamic token can cause OOS" errors 
"""

from __future__ import annotations

import re

from ..core import config, pdx

# "Token operation_steal_tech_airforce_cost is a dynamic token, ..."
# The game's log capitalizes "Token" at the start of the line but this has
# been inconsistent across patches, so match case-insensitively.
_ERROR_TOKEN_RE = re.compile(r"token\s+(\S+)\s+is a dynamic token", re.IGNORECASE)


def extract_tokens(text: str) -> list[str]:
    """Pull every distinct OOS-warning token name out of a block of text.

    Preserves first-seen order; used to sweep an entire error.log at once.
    """
    found = []
    for match in _ERROR_TOKEN_RE.finditer(text):
        tok = match.group(1)
        if tok not in found:
            found.append(tok)
    return found


def add_synchronized_token(token: str) -> bool:
    """Add `token` to synchronized_dynamic_tokens/tokens.txt if not already present.

    Returns True if it was added, False if it was already there.
    """
    path = config.synchronized_tokens_file()
    if not path.exists():
        text = ""
    else:
        text = pdx.read_text(path)
    existing = text.splitlines()
    if token in existing:
        return False
    if text == "" or text.endswith("\n"):
        sep = ""
    else:
        sep = "\n"
    new_text = text + sep + token + "\n"
    path.write_text(new_text, encoding="utf-8")
    return True


def verify_append_only() -> str:
    """Check that tokens.txt only changed by EOF appends relative to git HEAD.

    tokens.txt is positional across MP clients: reordering or mid-file inserts
    cause OOS. HEAD's content must be an exact prefix of the working copy.
    """
    import subprocess

    path = config.synchronized_tokens_file()
    if not path.exists():
        return "tokens.txt does not exist."
    current = pdx.read_text(path)
    rel = path.relative_to(config.mod_path())
    proc = subprocess.run(
        ["git", "-C", str(config.mod_path()), "show", f"HEAD:{rel.as_posix()}"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return f"Could not read HEAD version via git: {proc.stderr.strip()}"
    head = proc.stdout
    if current == head:
        return "tokens.txt is unchanged from HEAD."
    if current.startswith(head.rstrip("\n") + "\n") or current.startswith(head):
        added = current[len(head):].strip().splitlines()
        listing = "\n".join(f"  + {t}" for t in added)
        return f"OK: append-only. {len(added)} token(s) added at EOF:\n{listing}"
    # find the first diverging line for the report
    head_lines = head.splitlines()
    cur_lines = current.splitlines()
    for i, (a, b) in enumerate(zip(head_lines, cur_lines), 1):
        if a != b:
            return (
                f"DANGER: tokens.txt diverges from HEAD at line {i} "
                f"(HEAD: '{a}' vs working: '{b}'). Mid-file edits/reorders cause"
                " OOS in multiplayer - restore original ordering and re-append."
            )
    return (
        "DANGER: tokens.txt is SHORTER than HEAD (lines were removed)."
        " Removing tokens shifts every later token's id and causes OOS."
    )


def fix_all(text: str | None = None, log_path: str | None = None) -> str:
    """Extract every OOS dynamic-token warning from pasted text or an error.log and fix them all.

    If `text` is given it's scanned directly (e.g. a pasted warning or snippet
    of log output). Otherwise reads the error.log at `log_path` (or the
    configured/default location). Returns a summary of which tokens were
    newly added vs. already registered.
    """
    if text is None:
        path = config.log_file(log_path)
        if not path.exists():
            raise FileNotFoundError(f"Log file not found: {path}")
        text = path.read_text(encoding="utf-8", errors="replace")
        source = str(path)
    else:
        source = "pasted text"

    found = extract_tokens(text)
    if not found:
        return f"No OOS dynamic-token warnings found in {source}."

    added = []
    already = []
    for token in found:
        was_added = add_synchronized_token(token)
        if was_added:
            added.append(token)
        else:
            already.append(token)

    lines = []
    lines.append(f"Scanned {source} - found {len(found)} distinct token(s).")
    if len(added) > 0:
        lines.append(f"Added ({len(added)}): {', '.join(added)}")
    if len(already) > 0:
        lines.append(f"Already registered ({len(already)}): {', '.join(already)}")
    return "\n".join(lines)
