"""Create/delete US legislation entries (the congress bill system) in order to reduce manual writing of boilerplate.
One bill token touches:

  1. common/synchronized_dynamic_tokens/tokens.txt        - token registered (EOF append)
  2. common/scripted_localisation/OTH_USA_legislation_loc.txt
       - get_<token>_phase / _votes / _attributes / _sponsor defined_texts
       - one entry in each of the four bill dispatchers
  3. common/scripted_effects/OTH_USA_legislation_effects.txt - <token>_effect
  4. common/decisions/OTH_USA.txt                         - <token>_mission under USA_congress_management
  5. localisation/english/OTH_USA_l_english.yml           - <token>, <token>_mission, <token>_mission_desc, <token>.tt
"""

from __future__ import annotations

import re
from pathlib import Path

from ..core import config, pdx
from . import blocks, tokens

SCRIPTED_LOC_REL = "common/scripted_localisation/OTH_USA_legislation_loc.txt"
EFFECTS_REL = "common/scripted_effects/OTH_USA_legislation_effects.txt"
DECISIONS_REL = "common/decisions/OTH_USA.txt"
LOC_REL = "localisation/english/OTH_USA_l_english.yml"

DECISION_CATEGORY = "USA_congress_management"

# dispatcher name -> the variable its entries compare against
DISPATCHERS = {
    "get_bill_phase_display": ("bill_token", "phase"),
    "get_bill_votes_display": ("bill_token", "votes"),
    "get_selected_bill_phase_display": ("bill_token_scoped", "phase"),
    "get_selected_bill_votes_display": ("bill_token_scoped", "votes"),
}

_TOKEN_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _scripted_loc_blocks(token: str) -> str:
    """The four per-bill defined_text blocks, matching the file's existing style."""
    t = token
    return f"""defined_text = {{
	name = get_{t}_phase
	text = {{
		trigger = {{ set_temp_variable = {{ phase_v = phase@token:{t} }} }}
		localization_key = "[?phase_v.GetTokenLocalizedKey]"
	}}
}}
defined_text = {{
	name = get_{t}_votes
	text = {{
		trigger = {{
			check_variable = {{ phase@token:{t} = token:execution }}
			set_temp_variable = {{ senate_yea_v = senate_final_yea@token:{t} }}
			set_temp_variable = {{ senate_nay_v = senate_final_nay@token:{t} }}
			set_temp_variable = {{ house_yea_v = house_final_yea@token:{t} }}
			set_temp_variable = {{ house_nay_v = house_final_nay@token:{t} }}
		}}
		localization_key = USA_bill_vote_tally_both_final
	}}
	text = {{
		trigger = {{
			check_variable = {{ phase@token:{t} = token:house_vote }}
			check_variable = {{ source@token:{t} = token:senate }}
			set_temp_variable = {{ senate_yea_v = senate_final_yea@token:{t} }}
			set_temp_variable = {{ senate_nay_v = senate_final_nay@token:{t} }}
			set_temp_variable = {{ house_yea_v = house_yea@token:{t} }}
			set_temp_variable = {{ house_nay_v = house_nay@token:{t} }}
		}}
		localization_key = USA_bill_vote_tally_senate_final_house_projected
	}}
	text = {{
		trigger = {{
			check_variable = {{ phase@token:{t} = token:senate_vote }}
			check_variable = {{ source@token:{t} = token:house }}
			set_temp_variable = {{ house_yea_v = house_final_yea@token:{t} }}
			set_temp_variable = {{ house_nay_v = house_final_nay@token:{t} }}
			set_temp_variable = {{ senate_yea_v = senate_yea@token:{t} }}
			set_temp_variable = {{ senate_nay_v = senate_nay@token:{t} }}
		}}
		localization_key = USA_bill_vote_tally_house_final_senate_projected
	}}
	text = {{
		trigger = {{
			set_temp_variable = {{ senate_yea_v = senate_yea@token:{t} }}
			set_temp_variable = {{ senate_nay_v = senate_nay@token:{t} }}
			set_temp_variable = {{ house_yea_v = house_yea@token:{t} }}
			set_temp_variable = {{ house_nay_v = house_nay@token:{t} }}
		}}
		localization_key = USA_bill_vote_tally_both_projected
	}}
}}
defined_text = {{
	name = get_{t}_attributes
	text = {{
		trigger = {{
			set_temp_variable = {{ bill_attr_ref = token:{t} }}
			check_variable = {{ attributes@var:bill_attr_ref^num > 2 }}
			set_temp_variable = {{ attr_v_0 = attributes@var:bill_attr_ref^0 }}
			set_temp_variable = {{ attr_v_1 = attributes@var:bill_attr_ref^1 }}
			set_temp_variable = {{ attr_v_2 = attributes@var:bill_attr_ref^2 }}
		}}
		localization_key = USA_bill_attribute_list_3
	}}
	text = {{
		trigger = {{
			set_temp_variable = {{ bill_attr_ref = token:{t} }}
			check_variable = {{ attributes@var:bill_attr_ref^num > 1 }}
			set_temp_variable = {{ attr_v_0 = attributes@var:bill_attr_ref^0 }}
			set_temp_variable = {{ attr_v_1 = attributes@var:bill_attr_ref^1 }}
		}}
		localization_key = USA_bill_attribute_list_2
	}}
	text = {{
		trigger = {{
			set_temp_variable = {{ bill_attr_ref = token:{t} }}
			check_variable = {{ attributes@var:bill_attr_ref^num > 0 }}
			set_temp_variable = {{ attr_v_0 = attributes@var:bill_attr_ref^0 }}
		}}
		localization_key = USA_bill_attribute_list_1
	}}
	text = {{
		localization_key = ""
	}}
}}
defined_text = {{
	name = get_{t}_sponsor
	text = {{
		trigger = {{ set_temp_variable = {{ sponsor_v = sponsor@token:{t} }} }}
		localization_key = "[?sponsor_v.GetTokenLocalizedKey]"
	}}
}}"""


def _dispatcher_entry(token: str, var: str, kind: str) -> str:
    return (
        f"\ttext = {{\n"
        f"\t\ttrigger = {{ check_variable = {{ {var} = token:{token} }} }}\n"
        f'\t\tlocalization_key = "[get_{token}_{kind}]"\n'
        f"\t}}\n"
    )


def _effect_block(token: str) -> str:
    return f"{token}_effect = {{\n\tcustom_effect_tooltip = {token}.tt\n}}"


def _mission_block(token: str, timeout_days: int) -> str:
    t = token
    return f"""	{t}_mission = {{
		allowed = {{
			original_tag = USA
		}}
		days_mission_timeout = {timeout_days}
		is_good = yes
		activation = {{ always = no }}
		available = {{ always = no }}
		cancel_trigger = {{
			NOT = {{ is_in_array = {{ active_legislation = token:{t} }} }}
		}}
		timeout_effect = {{
			set_temp_variable = {{ temp_bill = token:{t} }}
			effect_tooltip = {{ # the signing event will execute this effect
				{t}_effect = yes
			}}
			kill_legislation = yes
		}}
	}}
"""


def _mission_desc_boilerplate(token: str, prose: str) -> str:
    return (
        f"{prose}\\n\\nCurrent Stage: §Y[get_{token}_phase]§!\\n[get_{token}_votes]"
        f"\\n\\nAttributes: [get_{token}_attributes]\\nSponsored by: §Y[get_{token}_sponsor]§!"
    )


def _introduce_snippet(token: str) -> str:
    """Not written anywhere - returned for pasting into the focus/event that spawns the bill."""
    return f"""set_temp_variable = {{ temp_bill = token:{token} }}
set_temp_variable = {{ sponsor = token:USA_SOME_SPONSOR }}
set_temp_variable = {{ initial_phase = token:writing }}
set_temp_variable = {{ temp_type = token:normal }}
set_temp_variable = {{ temp_bill_source = token:senate }}
# optional: add_to_temp_array = {{ temp_bill_array = token:USA_high_spending_bill_attribute }}
initialize_legislation = yes
activate_mission = {token}_mission"""


# --- block-location helpers -------------------------------------------------

def _find_named_defined_text(lines: list[str], name: str) -> tuple[int, int] | None:
    """(start, end) line indices of the defined_text block whose name = <name>."""
    name_re = re.compile(rf'\bname\s*=\s*"?{re.escape(name)}"?\s*$')
    for i, line in enumerate(lines):
        if name_re.search(blocks._strip_comment(line).rstrip()):
            # walk back to the enclosing block's opening line
            j, depth = i, 0
            while j >= 0:
                cleaned = blocks._strip_comment(lines[j])
                depth += cleaned.count("}") - cleaned.count("{")
                if depth < 0:
                    break
                j -= 1
            if j < 0:
                return None
            start = j
            depth = 0
            for k in range(start, len(lines)):
                cleaned = blocks._strip_comment(lines[k])
                depth += cleaned.count("{") - cleaned.count("}")
                if depth == 0:
                    return (start, k)
            return None
    return None


def _find_script_block(lines: list[str], header: str) -> tuple[int, int] | None:
    """(start, end) of a `<header> = {` script block."""
    header_re = re.compile(rf"^\s*{re.escape(header)}\s*=\s*\{{")
    for i, line in enumerate(lines):
        if header_re.match(blocks._strip_comment(line)):
            depth = 0
            for k in range(i, len(lines)):
                cleaned = blocks._strip_comment(lines[k])
                depth += cleaned.count("{") - cleaned.count("}")
                if depth == 0:
                    return (i, k)
            return None
    return None


def _sub_blocks(lines: list[str], start: int, end: int) -> list[tuple[int, int]]:
    """Top-level `text = { ... }` sub-block ranges inside a defined_text block."""
    ranges = []
    depth = 0
    sub_start = None
    for i in range(start, end + 1):
        cleaned = blocks._strip_comment(lines[i])
        for ch in cleaned:
            if ch == "{":
                depth += 1
                if depth == 2 and sub_start is None:
                    sub_start = i
            elif ch == "}":
                if depth == 2 and sub_start is not None:
                    ranges.append((sub_start, i))
                    sub_start = None
                depth -= 1
    return ranges


# --- create -----------------------------------------------------------------

def create(
    token: str,
    name: str | None = None,
    mission_desc: str | None = None,
    effect_tooltip: str | None = None,
    timeout_days: int = 120,
    dry_run: bool = False,
) -> str:
    if not _TOKEN_RE.match(token) and not re.match(r"^[A-Z]{3}_[a-z0-9_]+$", token):
        return (
            f"'{token}' doesn't look like a bill token (expected lowercase snake_case, "
            "optionally with a USA_ prefix, e.g. 'USA_clean_air_act')."
        )

    mod = config.mod_path()
    loc_script_path = mod / SCRIPTED_LOC_REL
    effects_path = mod / EFFECTS_REL
    decisions_path = mod / DECISIONS_REL
    loc_path = mod / LOC_REL
    for p, rel in ((loc_script_path, SCRIPTED_LOC_REL), (effects_path, EFFECTS_REL),
                   (decisions_path, DECISIONS_REL), (loc_path, LOC_REL)):
        if not p.exists():
            return f"Expected file missing from mod: {rel}"

    loc_script_text = pdx.read_text(loc_script_path)
    if re.search(rf"\bname\s*=\s*get_{re.escape(token)}_phase\b", loc_script_text):
        return f"A legislation '{token}' already exists (get_{token}_phase is defined). Nothing written."

    # localisation values: generic placeholders unless wording was supplied
    # verbatim (same no-AI-prose policy as create_event).
    display = name or f"PLACEHOLDER_{token}"
    prose = mission_desc or f"PLACEHOLDER_{token}_mission_desc"
    tt = effect_tooltip or f"PLACEHOLDER_{token}_effect_tooltip"
    loc_entries = [
        (token, display),
        (f"{token}_mission", f"${token}$"),
        (f"{token}_mission_desc", _mission_desc_boilerplate(token, prose)),
        (f"{token}.tt", tt),
    ]

    if dry_run:
        preview = [
            f"[dry run] Would create legislation '{token}' across 5 files:",
            f"1. tokens.txt: append '{token}' at EOF (skipped if already registered)",
            f"2. {SCRIPTED_LOC_REL}: append 4 defined_texts + add an entry to each of "
            f"the {len(DISPATCHERS)} bill dispatchers",
            f"3. {EFFECTS_REL}: append:\n{_effect_block(token)}",
            f"4. {DECISIONS_REL}: insert under {DECISION_CATEGORY}:\n{_mission_block(token, timeout_days)}",
            "5. " + LOC_REL + ": append:\n" + "\n".join(f'  {k}: "{v}"' for k, v in loc_entries),
            "",
            "Paste this where the bill should be introduced (focus/event/decision):",
            _introduce_snippet(token),
        ]
        return "\n".join(preview)

    # 1. token registration (EOF append only - positional file)
    token_added = tokens.add_synchronized_token(token)

    # 2a. per-bill defined_texts
    pdx.append_script_block(loc_script_path, _scripted_loc_blocks(token))

    # 2b. dispatcher entries - insert right after the dispatcher's `name =` line
    # so the empty-key fallback stays last
    lines = pdx.read_text(loc_script_path).splitlines(keepends=True)
    missing_dispatchers = []
    for disp, (var, kind) in DISPATCHERS.items():
        span = _find_named_defined_text(lines, disp)
        if span is None:
            missing_dispatchers.append(disp)
            continue
        name_re = re.compile(rf"\bname\s*=\s*{re.escape(disp)}\b")
        for i in range(span[0], span[1] + 1):
            if name_re.search(lines[i]):
                lines.insert(i + 1, _dispatcher_entry(token, var, kind))
                break
    loc_script_path.write_text("".join(lines), encoding="utf-8")

    # 3. scripted effect
    pdx.append_script_block(effects_path, _effect_block(token))

    # 4. mission decision under the congress category
    dec_lines = pdx.read_text(decisions_path).splitlines(keepends=True)
    cat_span = _find_script_block(dec_lines, DECISION_CATEGORY)
    mission_written = cat_span is not None
    if mission_written:
        dec_lines.insert(cat_span[1], _mission_block(token, timeout_days) + "\n")
        decisions_path.write_text("".join(dec_lines), encoding="utf-8")

    # 5. loc keys, matching the file's existing `key: "value"` style
    loc_text = pdx.read_text(loc_path)
    new_loc = loc_text.rstrip("\n") + "\n" + "\n".join(
        f'{k}: "{v}"' for k, v in loc_entries
    ) + "\n"
    loc_path.write_text(new_loc, encoding="utf-8-sig")

    report = [f"Created legislation '{token}':"]
    report.append(
        f"  + tokens.txt: '{token}' " + ("appended at EOF" if token_added else "was already registered")
    )
    report.append(f"  + {SCRIPTED_LOC_REL}: 4 defined_texts + {len(DISPATCHERS) - len(missing_dispatchers)} dispatcher entries")
    if missing_dispatchers:
        report.append(f"  ! dispatchers not found (entry NOT added): {', '.join(missing_dispatchers)}")
    report.append(f"  + {EFFECTS_REL}: {token}_effect (placeholder - put the real effect here)")
    if mission_written:
        report.append(f"  + {DECISIONS_REL}: {token}_mission under {DECISION_CATEGORY} (timeout {timeout_days}d)")
    else:
        report.append(f"  ! {DECISION_CATEGORY} category not found in {DECISIONS_REL} - mission NOT written")
    report.append(f"  + {LOC_REL}: {len(loc_entries)} keys" + ("" if name else " (PLACEHOLDER prose - fill in by hand)"))
    report.append("")
    report.append(blocks.validate_file(SCRIPTED_LOC_REL))
    report.append(blocks.validate_file(DECISIONS_REL))
    report.append(blocks.validate_file(EFFECTS_REL))
    report.append("")
    report.append("Paste this where the bill should be introduced (focus/event/decision):")
    report.append(_introduce_snippet(token))
    return "\n".join(report)


# --- delete -----------------------------------------------------------------

def delete(token: str, dry_run: bool = False) -> str:
    mod = config.mod_path()
    actions: list[str] = []

    # scripted loc: the four defined_texts + dispatcher entries
    loc_script_path = mod / SCRIPTED_LOC_REL
    lines = pdx.read_text(loc_script_path).splitlines(keepends=True)
    removed_defined = []
    for suffix in ("phase", "votes", "attributes", "sponsor"):
        span = _find_named_defined_text(lines, f"get_{token}_{suffix}")
        if span:
            del lines[span[0]:span[1] + 1]
            removed_defined.append(f"get_{token}_{suffix}")
    removed_dispatch = []
    token_ref = re.compile(rf"\btoken:{re.escape(token)}\b")
    for disp in DISPATCHERS:
        span = _find_named_defined_text(lines, disp)
        if span is None:
            continue
        for sub in reversed(_sub_blocks(lines, span[0], span[1])):
            if any(token_ref.search(lines[i]) for i in range(sub[0], sub[1] + 1)):
                del lines[sub[0]:sub[1] + 1]
                removed_dispatch.append(disp)
    if removed_defined or removed_dispatch:
        new_text = "".join(lines)
        opens, closes = blocks.brace_report(new_text)
        if opens != closes:
            return (
                f"ABORTED: removing '{token}' from {SCRIPTED_LOC_REL} would leave it "
                f"unbalanced ({opens} vs {closes}). No files were changed."
            )
        if not dry_run:
            loc_script_path.write_text(new_text, encoding="utf-8")
        actions.append(
            f"{SCRIPTED_LOC_REL}: removed {len(removed_defined)} defined_texts "
            f"({', '.join(removed_defined) or 'none'}) + {len(removed_dispatch)} dispatcher entries"
        )

    # scripted effect + mission decision (blocks.remove_block is brace-safe)
    for rel, block_name in ((EFFECTS_REL, f"{token}_effect"), (DECISIONS_REL, f"{token}_mission")):
        result = blocks.remove_block(rel, block_name, dry_run)
        if "No block named" not in result:
            actions.append(result)

    # loc keys
    loc_path = mod / LOC_REL
    loc_keys = {token, f"{token}_mission", f"{token}_mission_desc", f"{token}.tt", f"{token}_mission.tt", f"{token}_mission_desc.tt"}
    key_re = re.compile(rf"^\s*({'|'.join(re.escape(k) for k in loc_keys)})\s*:")
    loc_lines = pdx.read_text(loc_path).splitlines(keepends=True)
    kept = [l for l in loc_lines if not key_re.match(l)]
    n_loc = len(loc_lines) - len(kept)
    if n_loc:
        if not dry_run:
            loc_path.write_text("".join(kept), encoding="utf-8-sig")
        actions.append(f"{LOC_REL}: removed {n_loc} loc line(s)")

    if not actions:
        return f"No trace of legislation '{token}' found - nothing to delete."

    prefix = "[dry run] Would delete" if dry_run else "Deleted"
    notes = [
        f"{prefix} legislation '{token}':",
        *[f"  - {a}" for a in actions],
        "",
        f"NOTE: '{token}' was NOT removed from tokens.txt - that file is positional/"
        "append-only and removing lines causes OOS. A dead token entry is harmless.",
        f"Check by hand for introduce-sites (initialize_legislation / activate_mission = "
        f"{token}_mission) in focuses/events - those are bespoke and not touched.",
    ]
    if not dry_run:
        notes.append(blocks.validate_file(SCRIPTED_LOC_REL))
    return "\n".join(notes)
