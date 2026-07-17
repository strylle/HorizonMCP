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
from . import blocks, tokens

_REGISTER_RE = re.compile(
    r"set_temp_variable\s*=\s*\{\s*pseudodecision\s*=\s*token:([A-Za-z0-9_]+)\s*\}"
)
_EFFECT_TOKEN_RE = re.compile(r"\{\s*effects\s*=\s*token:([A-Za-z0-9_]+)\s*\}")
_TRIGGER_TOKEN_RE = re.compile(r"\{\s*triggers\s*=\s*token:([A-Za-z0-9_]+)\s*\}")
_MISSION_TIMEOUT_RE = re.compile(r"\{\s*mission_days_timeout\s*=\s*(\d+)")
_RECURRING_RE = re.compile(r"\{\s*recurring_aid\s*=\s*1\s*\}")
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
    mission_days: int | None = None
    recurring: bool = False


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
            mt = _MISSION_TIMEOUT_RE.search(line)
            if mt:
                current.mission = True
                current.mission_days = int(mt.group(1))
            if _RECURRING_RE.search(line):
                current.recurring = True
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


def _extract_named_block(directory: Path, name: str) -> str | None:
    """Text of the first `<name> = { ... }` block found in any .txt under directory."""
    if not directory.is_dir():
        return None
    header_re = re.compile(rf"^\s*{re.escape(name)}\s*=\s*\{{")
    for path in sorted(directory.rglob("*.txt")):
        try:
            lines = pdx.read_text(path).splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines):
            if header_re.match(blocks._strip_comment(line)):
                depth = 0
                for k in range(i, len(lines)):
                    cleaned = blocks._strip_comment(lines[k])
                    depth += cleaned.count("{") - cleaned.count("}")
                    if depth == 0:
                        return "\n".join(lines[i:k + 1])
                return None
    return None


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
        if reg.mission and reg.token in decision_defs:
            block = _extract_named_block(root / "common" / "decisions", reg.token) or ""
            m = re.search(r"\bdays_mission_timeout\s*=\s*(\d+)", block)
            if m and reg.mission_days is not None and int(m.group(1)) != reg.mission_days:
                problems.append(
                    f"registration mission_days_timeout ({reg.mission_days}) != backing "
                    f"mission days_mission_timeout ({m.group(1)}) - GUI progress bar will be wrong"
                )
            if reg.recurring and not re.search(
                rf"\bactivate_mission\s*=\s*{re.escape(reg.token)}\b", block
            ):
                problems.append(
                    "recurring mission does not self-reactivate (timeout_effect lacks "
                    f"'activate_mission = {reg.token}')"
                )
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


# --- create / delete ---------------------------------------------------------

IDEAS_REL = "common/ideas/_proxy_init_ideas.txt"
DECISIONS_REL = "common/decisions/OTH_proxy_wars.txt"
CATEGORIES_REL = "common/decisions/categories/proxy_war_categories.txt"
PAYLOADS_REL = "common/scripted_effects/OTH_proxy_pseudodecision_payloads.txt"
TRIGGERS_REL = "common/scripted_triggers/OTH_proxy_pseudodecision_triggers.txt"
LOC_REL = "localisation/english/OTH_proxy_wars_l_english.yml"

VALID_EFFECTS = ("complete_effect", "remove_effect", "cancel_effect", "timeout_effect")
VALID_TRIGGERS = ("visible", "available", "activation", "custom_cost_trigger")

_TOKEN_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _registration_lines(
    token: str, mission: bool, effects: list[str], triggers: list[str],
    cost: int | None, intel_base_cost: int | None,
    days_remove: int, days_re_enable: int,
    mission_days_timeout: int, mission_is_good: bool, recurring: bool,
    fire_only_once: bool, ai_will_do: int | None,
) -> list[str]:
    out = [f"set_temp_variable = {{ pseudodecision = token:{token} }}"]
    out += [f"add_to_temp_array = {{ effects = token:{e} }}" for e in effects]
    out += [f"add_to_temp_array = {{ triggers = token:{t} }}" for t in triggers]
    if intel_base_cost is not None:
        out.append("set_temp_variable = { custom_cost_text = token:OTH_intel_cost }")
        out.append(f"set_temp_variable = {{ intel_base_cost = {intel_base_cost} }}")
    elif cost is not None:
        out.append(f"set_temp_variable = {{ cost = {cost} }}")
    if mission:
        out.append(f"set_temp_variable = {{ mission_days_timeout = {mission_days_timeout} }}")
        out.append("set_temp_variable = { mission_selectable = 1 }")
        if mission_is_good:
            out.append("set_temp_variable = { mission_is_good = 1 }")
        if recurring:
            out.append("set_temp_variable = { recurring_aid = 1 }")
    else:
        out.append(f"set_temp_variable = {{ days_re_enable = {days_re_enable} }}")
        out.append(f"set_temp_variable = {{ days_remove = {days_remove} }}")
    if fire_only_once:
        out.append("set_temp_variable = { fire_only_once = 1 }")
    if ai_will_do is not None:
        out.append(f"set_temp_variable = {{ ai_will_do = {ai_will_do} }}")
    out.append(f"{_INIT_CALL} = yes")
    return out


def _decision_blocks(
    token: str, mission: bool, effects: list[str],
    cost: int | None, intel: bool,
    days_remove: int, days_re_enable: int,
    mission_days_timeout: int, mission_is_good: bool, recurring: bool,
    fire_only_once: bool,
) -> str:
    if mission:
        lines = [f"\t{token} = {{"]
        lines.append("\t\tactivation = { always = no }")
        lines.append("\t\tavailable = { always = no }")
        lines.append(f"\t\tdays_mission_timeout = {mission_days_timeout}")
        lines.append(f"\t\tis_good = {'yes' if mission_is_good else 'no'}")
        lines.append("\t\ttimeout_effect = {")
        lines.append(f"\t\t\t{token}_timeout_effect = yes")
        if recurring:
            lines.append("\t\t\thidden_effect = {")
            lines.append(f"\t\t\t\tactivate_mission = {token}")
            lines.append("\t\t\t}")
        lines.append("\t\t}")
        lines.append("\t}")
        return "\n".join(lines)
    lines = [f"\t{token} = {{"]
    if intel:
        lines.append("\t\tcustom_cost_trigger = {")
        lines.append(f"\t\t\t{token}_custom_cost_trigger = yes")
        lines.append("\t\t}")
        lines.append("\t\tcustom_cost_text = OTH_intel_cost")
    elif cost is not None:
        lines.append(f"\t\tcost = {cost}")
    lines.append(f"\t\tdays_remove = {days_remove}")
    lines.append(f"\t\tdays_re_enable = {days_re_enable}")
    if fire_only_once:
        lines.append("\t\tfire_only_once = yes")
    for e in effects:
        lines.append(f"\t\t{e} = {{")
        lines.append(f"\t\t\t{token}_{e} = yes")
        lines.append("\t\t}")
    lines.append("\t}")
    lines.append(
        f"\t{token}_timeout = {{ allowed = {{ always = no }} "
        f"available = {{ always = no }} days_mission_timeout = {days_remove} }}"
    )
    return "\n".join(lines)


def _payload_stub(token: str, effect: str, proxy: str, intel: bool) -> str:
    if intel and effect == "complete_effect":
        return (
            f"{token}_{effect} = {{\n"
            "\thidden_effect = {\n"
            f"\t\tset_temp_variable = {{ base_cost = OTH_intel_base_cost@token:{token} }}\n"
            f"\t\tset_temp_variable = {{ proxy = token:{proxy} }}\n"
            "\t\tOTH_spend_intel_currency = yes\n"
            "\t}\n"
            "}"
        )
    return f"{token}_{effect} = {{\n}}"


def _trigger_stub(token: str, trigger: str, proxy: str) -> str:
    if trigger == "custom_cost_trigger":
        return (
            f"{token}_custom_cost_trigger = {{\n"
            f"\tset_temp_variable = {{ base_cost = OTH_intel_base_cost@token:{token} }}\n"
            f"\tset_temp_variable = {{ proxy = token:{proxy} }}\n"
            "\tintel_cost_check = yes\n"
            "}"
        )
    return f"{token}_{trigger} = {{\n\talways = yes\n}}"


def _find_block_span(lines: list[str], header: str, start: int = 0, end: int | None = None) -> tuple[int, int] | None:
    header_re = re.compile(rf"^\s*{re.escape(header)}\s*=\s*\{{")
    end = len(lines) if end is None else end
    for i in range(start, end):
        if header_re.match(blocks._strip_comment(lines[i])):
            depth = 0
            for k in range(i, len(lines)):
                cleaned = blocks._strip_comment(lines[k])
                depth += cleaned.count("{") - cleaned.count("}")
                if depth == 0:
                    return (i, k)
            return None
    return None


def create(
    token: str,
    proxy: str,
    supporter: str,
    kind: str = "decision",
    effects: list[str] | None = None,
    triggers: list[str] | None = None,
    cost: int | None = None,
    intel_base_cost: int | None = None,
    days_remove: int = 30,
    days_re_enable: int = 30,
    mission_days_timeout: int = 31,
    mission_is_good: bool = True,
    recurring: bool = False,
    fire_only_once: bool = False,
    ai_will_do: int | None = None,
    dry_run: bool = False,
) -> str:
    if kind not in ("decision", "mission"):
        return f"kind must be 'decision' or 'mission', got '{kind}'."
    mission = kind == "mission"
    if not _TOKEN_NAME_RE.match(token):
        return f"'{token}' is not a valid token name."
    effects = list(effects) if effects else (["timeout_effect"] if mission else ["remove_effect"])
    triggers = list(triggers) if triggers else []
    intel = intel_base_cost is not None
    if intel and "custom_cost_trigger" not in triggers:
        triggers.append("custom_cost_trigger")
    bad = [e for e in effects if e not in VALID_EFFECTS] + [t for t in triggers if t not in VALID_TRIGGERS]
    if bad:
        return (
            f"Unknown effect/trigger token(s): {', '.join(bad)}. "
            f"Valid effects: {', '.join(VALID_EFFECTS)}; triggers: {', '.join(VALID_TRIGGERS)}."
        )
    if mission and "timeout_effect" not in effects:
        return "A mission-type pseudodecision needs timeout_effect in its effects."
    if intel and cost is not None:
        return "Pass either cost (political power) or intel_base_cost, not both."

    mod = config.mod_path()
    for rel in (IDEAS_REL, DECISIONS_REL, PAYLOADS_REL, TRIGGERS_REL, LOC_REL):
        if not (mod / rel).exists():
            return f"Expected file missing from mod: {rel}"

    ideas_path = mod / IDEAS_REL
    ideas_lines = pdx.read_text(ideas_path).splitlines(keepends=True)
    if any(f"token:{token} " in l or f"token:{token}}}" in l for l in ideas_lines):
        return f"'{token}' already appears in {IDEAS_REL}. Nothing written."
    proxy_span = _find_block_span(ideas_lines, proxy)
    if proxy_span is None:
        return f"Proxy token block '{proxy}' not found in {IDEAS_REL}."
    supp_span = _find_block_span(ideas_lines, supporter, proxy_span[0], proxy_span[1] + 1)
    if supp_span is None:
        return (
            f"Supporter block '{supporter} = {{' not found inside '{proxy}' in {IDEAS_REL}. "
            "Add the supporter to the proxy's on_add first."
        )
    indent = re.match(r"\s*", ideas_lines[supp_span[0]]).group(0).replace("\n", "") + "\t"
    reg_lines = _registration_lines(
        token, mission, effects, triggers, cost, intel_base_cost,
        days_remove, days_re_enable, mission_days_timeout, mission_is_good,
        recurring, fire_only_once, ai_will_do,
    )
    insert_at = supp_span[0] + 1
    for i in range(supp_span[0], supp_span[1] + 1):
        if "# Decisions" in ideas_lines[i]:
            insert_at = i + 1
            break
    reg_text = "".join(f"{indent}{l}\n" for l in reg_lines) + "\n"

    category = f"proxy_{proxy}_decisions"
    dec_path = mod / DECISIONS_REL
    dec_lines = pdx.read_text(dec_path).splitlines(keepends=True)
    cat_span = _find_block_span(dec_lines, category)
    dec_block = _decision_blocks(
        token, mission, effects, cost, intel, days_remove, days_re_enable,
        mission_days_timeout, mission_is_good, recurring, fire_only_once,
    )
    need_intel_dummy = intel and not any(
        re.match(r"\s*OTH_intel_cost\s*=\s*\{", blocks._strip_comment(l)) for l in dec_lines
    )
    if need_intel_dummy:
        dec_block += "\n\tOTH_intel_cost = { allowed = { always = no } }"

    payload_blocks = [_payload_stub(token, e, proxy, intel) for e in effects]
    trigger_blocks = [_trigger_stub(token, t, proxy) for t in triggers]
    loc_entries = [(token, f"PLACEHOLDER_{token}"), (f"{token}_desc", f"PLACEHOLDER_{token}_desc")]

    if dry_run:
        preview = [
            f"[dry run] Would create {kind}-type pseudodecision '{token}' "
            f"(proxy {proxy}, supporter {supporter}):",
            f"1. tokens.txt: append '{token}' at EOF",
            f"2. {IDEAS_REL}: insert at line {insert_at + 1} inside {supporter} block:",
            *(f"     {l}" for l in reg_lines),
            f"3. {DECISIONS_REL}: "
            + (f"append inside {category}:" if cat_span else f"create category {category} (+ register it in {CATEGORIES_REL}) containing:"),
            dec_block,
            f"4. {PAYLOADS_REL}: append {len(payload_blocks)} payload stub(s)",
            f"5. {TRIGGERS_REL}: append {len(trigger_blocks)} trigger stub(s)" if trigger_blocks else f"5. {TRIGGERS_REL}: nothing to add",
            f"6. {LOC_REL}: append " + ", ".join(k for k, _ in loc_entries),
        ]
        return "\n".join(preview)

    token_added = tokens.add_synchronized_token(token)

    ideas_lines.insert(insert_at, reg_text)
    ideas_path.write_text("".join(ideas_lines), encoding="utf-8")

    if cat_span:
        dec_lines.insert(cat_span[1], dec_block + "\n")
        dec_path.write_text("".join(dec_lines), encoding="utf-8")
        category_note = f"inside existing {category}"
    else:
        pdx.append_script_block(dec_path, f"{category} = {{\n{dec_block}\n}}")
        cats_path = mod / CATEGORIES_REL
        if cats_path.exists() and category not in pdx.read_text(cats_path):
            pdx.append_script_block(cats_path, f"{category} = {{\n\tallowed = {{ always = no }}\n}}")
        category_note = f"created new category {category} (registered in {CATEGORIES_REL})"

    for b in payload_blocks:
        pdx.append_script_block(mod / PAYLOADS_REL, b)
    for b in trigger_blocks:
        pdx.append_script_block(mod / TRIGGERS_REL, b)

    loc_path = mod / LOC_REL
    loc_text = pdx.read_text(loc_path).rstrip("\n")
    loc_text += "\n" + "\n".join(f'  {k}: "{v}"' for k, v in loc_entries) + "\n"
    loc_path.write_text(loc_text, encoding="utf-8-sig")

    report = [f"Created {kind}-type pseudodecision '{token}':"]
    report.append("  + tokens.txt: " + ("appended at EOF" if token_added else "already registered"))
    report.append(f"  + {IDEAS_REL}: registration in {supporter} block of {proxy}")
    report.append(f"  + {DECISIONS_REL}: backing {'mission' if mission else 'decision + _timeout dummy'} {category_note}")
    if need_intel_dummy:
        report.append(f"  + {DECISIONS_REL}: OTH_intel_cost dummy (was missing)")
    report.append(f"  + {PAYLOADS_REL}: {len(payload_blocks)} payload stub(s) - fill in the real effects")
    if trigger_blocks:
        report.append(f"  + {TRIGGERS_REL}: {len(trigger_blocks)} trigger stub(s)"
                      + (" (custom_cost_trigger is real, others are always=yes stubs)" if intel else " (always=yes stubs)"))
    report.append(f"  + {LOC_REL}: {len(loc_entries)} PLACEHOLDER keys - fill in by hand")
    report.append("")
    for rel in (IDEAS_REL, DECISIONS_REL, PAYLOADS_REL, TRIGGERS_REL):
        report.append(blocks.validate_file(rel))
    report.append("")
    report.append(check())
    return "\n".join(report)


def delete(token: str, dry_run: bool = False) -> str:
    mod = config.mod_path()
    actions: list[str] = []

    ideas_path = mod / IDEAS_REL
    if ideas_path.exists():
        lines = pdx.read_text(ideas_path).splitlines(keepends=True)
        start = next(
            (i for i, l in enumerate(lines)
             if _REGISTER_RE.search(blocks._strip_comment(l))
             and _REGISTER_RE.search(blocks._strip_comment(l)).group(1) == token),
            None,
        )
        if start is not None:
            end = next(
                (k for k in range(start, len(lines)) if _INIT_CALL in lines[k]), None
            )
            if end is not None:
                del_end = end
                if del_end + 1 < len(lines) and lines[del_end + 1].strip() == "":
                    del_end += 1
                new_text = "".join(lines[:start] + lines[del_end + 1:])
                opens, closes = blocks.brace_report(new_text)
                if opens != closes:
                    return (
                        f"ABORTED: removing the registration would unbalance {IDEAS_REL} "
                        f"({opens} vs {closes}). No files were changed."
                    )
                if not dry_run:
                    ideas_path.write_text(new_text, encoding="utf-8")
                actions.append(f"{IDEAS_REL}: removed registration (lines {start + 1}-{end + 1})")

    for name in (token, f"{token}_timeout"):
        result = blocks.remove_block(DECISIONS_REL, name, dry_run)
        if "No block named" not in result:
            actions.append(result)

    for suffix in VALID_EFFECTS:
        result = blocks.remove_block(PAYLOADS_REL, f"{token}_{suffix}", dry_run)
        if "No block named" not in result:
            actions.append(result)
    for suffix in VALID_TRIGGERS:
        result = blocks.remove_block(TRIGGERS_REL, f"{token}_{suffix}", dry_run)
        if "No block named" not in result:
            actions.append(result)

    loc_path = mod / LOC_REL
    if loc_path.exists():
        key_re = re.compile(rf"^\s*{re.escape(token)}(_desc)?\s*:")
        loc_lines = pdx.read_text(loc_path).splitlines(keepends=True)
        kept = [l for l in loc_lines if not key_re.match(l)]
        n_loc = len(loc_lines) - len(kept)
        if n_loc:
            if not dry_run:
                loc_path.write_text("".join(kept), encoding="utf-8-sig")
            actions.append(f"{LOC_REL}: removed {n_loc} loc line(s)")

    if not actions:
        return f"No trace of pseudodecision '{token}' found - nothing to delete."

    prefix = "[dry run] Would delete" if dry_run else "Deleted"
    notes = [
        f"{prefix} pseudodecision '{token}':",
        *[f"  - {a}" for a in actions],
        "",
        f"NOTE: '{token}' was NOT removed from tokens.txt - that file is positional/"
        "append-only and removing lines causes OOS. A dead token entry is harmless.",
        "Check by hand for bespoke references (GUI arrays, events, focuses) - not touched.",
    ]
    if not dry_run:
        for rel in (IDEAS_REL, DECISIONS_REL, PAYLOADS_REL, TRIGGERS_REL):
            notes.append(blocks.validate_file(rel))
    return "\n".join(notes)
