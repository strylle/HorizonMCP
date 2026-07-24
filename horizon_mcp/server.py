"""
HorizonMCP server
"""

# docustrings are LLM generated as it's the AI using it anyway

from __future__ import annotations
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from .core import config, pdx
from .tools import blocks, changed, events, gfx, legislation, lint, pseudo, tokens, varflow

mcp = FastMCP(
    "horizon-mcp",
    instructions=(
        "HOI4 scripting uncertainty: check hoi4_scripting_gotchas first "
        "(silent-failure engine quirks). If still unsure, search the official "
        "wiki (hoi4.paradoxwikis.com) before guessing."
    ),
)

GOTCHAS_PATH = Path(__file__).parent / "docs" / "gotchas.md"


@mcp.resource("horizon://gotchas")
def gotchas_resource() -> str:
    """HOI4 scripting gotchas: engine behaviors that fail silently."""
    return GOTCHAS_PATH.read_text()


@mcp.tool()
def hoi4_scripting_gotchas() -> str:
    """Silent-failure HOI4 script gotchas: temp var shadowing, scope chain-reads,
    variable tooltips, check_variable compare, loc/gui trigger limits, effectFile
    scale, global.date scale, iconType orientation. Call before novel script here.
    """
    return GOTCHAS_PATH.read_text()


@mcp.tool()
def list_event_namespaces() -> str:
    """List event namespaces + declaring file. Check before create_event."""
    ns_map = pdx.index_event_namespaces()
    if not ns_map:
        return "No event namespaces found."
    lines = []
    for ns, path in sorted(ns_map.items()):
        lines.append(f"{ns}\t{path.name}")
    return "\n".join(lines)


@mcp.tool()
def next_event_id(namespace: str) -> str:
    """Return the next free event id for a namespace, e.g. 'usa_flavor.12'."""
    ns_map = pdx.index_event_namespaces()
    if namespace not in ns_map:
        return f"Namespace '{namespace}' not found. Use list_event_namespaces."
    n = pdx.find_next_event_id(ns_map[namespace], namespace)
    return f"{namespace}.{n}"


@mcp.tool()
def create_event(
    namespace: str,
    options: list[events.EventOption],
    title: str | None = None,
    desc: str | None = None,
    event_type: str = "country",
    picture: str | None = None,
    is_triggered_only: bool = True,
    trigger: str | None = None,
    mean_time_to_happen: str | None = None,
    target_file: str | None = None,
    loc_file: str | None = None,
    placeholder_loc: bool = True,
    dry_run: bool = False,
) -> str:
    """Create a HOI4 event: script block + loc. Id auto-assigned (next free in namespace).

    Default placeholder_loc=True writes PLACEHOLDER_* text (no-AI-prose policy);
    pass False + explicit title/desc/option.name only with verbatim wording.
    New namespace: pass target_file. dry_run=True previews without writing.
    """
    result = events.create_event(
        namespace=namespace, title=title, desc=desc, options=options,
        event_type=event_type, picture=picture,
        is_triggered_only=is_triggered_only, trigger=trigger,
        mean_time_to_happen=mean_time_to_happen, target_file=target_file,
        loc_file=loc_file, placeholder_loc=placeholder_loc, dry_run=dry_run,
    )
    return result.summary()


@mcp.tool()
def fix_oos_tokens(text: str | None = None, log_path: str | None = None) -> str:
    """Fix "dynamic token can cause OOS" warnings by registering them.

    Pass `text` to scan a pasted warning/log snippet, or omit to scan error.log
    (LOG_PATH env or standard macOS Paradox path, override with log_path).
    Appends new tokens to tokens.txt; no-op for already-registered ones.
    """
    return tokens.fix_all(text=text, log_path=log_path)


@mcp.tool()
def check_script(file: str | None = None, checks: list[str] | None = None) -> str:
    """Brace balance + GFX_ sprite refs + trigger-context lint, one call.

    `checks`: subset of ["braces","gfx","triggers"] (default all three). Pass
    `file` (mod-relative) to scope to one file; omit for each check's own
    whole-mod sweep (braces: .txt/.gui/.gfx under common/events/interface;
    gfx: .gui + scripted_guis, mod .gfx + vanilla via GAME_PATH; triggers:
    scripted_guis + scripted_triggers, effects-in-trigger-context + unguarded
    divide). Run after any hand edit or block removal.
    """
    want = checks or ["braces", "gfx", "triggers"]
    parts = []
    if "braces" in want:
        parts.append(blocks.validate_file(file) if file else blocks.validate_all())
    if "gfx" in want:
        parts.append(gfx.check_file(file) if file else gfx.check_all())
    if "triggers" in want:
        parts.append(lint.lint(file))
    return "\n\n".join(parts)


@mcp.tool()
def lint_changed_files(against: str = "HEAD") -> str:
    """Run brace/gfx-ref/trigger-context/tokens-append checks on git-changed
    files only (working tree vs `against`, plus untracked). Cheap, quiet
    default for "did I just break anything" - use check_script for a whole-mod
    pass. Does NOT cover check_variable_flow/check_pseudodecisions - those need
    whole-mod scope to be correct.
    """
    return changed.check(against)


@mcp.tool()
def remove_named_block(file: str, name: str, dry_run: bool = False) -> str:
    """Remove one named block from a Paradox script/gui file, brace-safely.

    `name` matches a gui `name = "<name>"` block or a `<name> = {` script header.
    Refuses if ambiguous or file unbalanced. dry_run=True previews (line range +
    first lines) without writing.
    """
    return blocks.remove_block(file, name, dry_run)


@mcp.tool()
def check_variable_flow(prefix: str | None = None) -> str:
    """Cross-reference dynamic variable/array writes vs reads (common/, events/, loc [?var]).

    Reports WRITE-ONLY (dead data) and READ-ONLY (fed by nothing) variables.
    Pass `prefix` (e.g. 'OTH_proxy') to scope the report, omit for a full
    (noisier) sweep. Lexical, not semantic - treat findings as leads, not verdicts.
    """
    return varflow.check_flow(prefix)


@mcp.tool()
def check_tokens_append_only() -> str:
    """Verify tokens.txt only changed by EOF appends since git HEAD.

    Positional across MP clients: reorder/insert/delete shifts token ids -> OOS.
    Run before committing any change touching it.
    """
    return tokens.verify_append_only()


@mcp.tool()
def add_synchronized_token(token: str) -> str:
    """Append a token to tokens.txt at EOF (the only safe place; no-op if already
    registered). Use instead of hand-editing - mid-file inserts cause MP OOS."""
    added = tokens.add_synchronized_token(token)
    if added:
        return f"Added '{token}' at EOF of synchronized_dynamic_tokens/tokens.txt"
    return f"'{token}' is already registered, no change made."


@mcp.tool()
def check_pseudodecisions() -> str:
    """Verify every pseudodecision's six-file contract (OTH_init_proxy_pseudodecision
    in common/ideas): token in tokens.txt; <token>_<suffix> effect/trigger per
    effects/triggers key; backing decision + <token>_timeout dummy in
    common/decisions (missions exempt from dummy); loc keys <token>/<token>_desc.
    Missing legs fail silently in-game - run after add/rename.
    """
    return pseudo.check()


@mcp.tool()
def create_proxy_pseudodecision(
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
    """Create a proxy-war pseudodecision: all six contract files at once.

    Writes registration under `supporter` in `proxy`'s on_add (_proxy_init_ideas.txt),
    backing decision+_timeout dummy or mission (OTH_proxy_wars.txt), payload/trigger
    stubs, PLACEHOLDER loc keys (<token>, <token>_desc - no-AI-prose policy), and
    registers the token at tokens.txt EOF.

    kind='decision': uses days_remove/days_re_enable; cost (PP) OR intel_base_cost
    (wires custom_cost_trigger + OTH_intel_cost text/dummy decision +
    OTH_spend_intel_currency in complete_effect).
    kind='mission': uses mission_days_timeout/mission_is_good; effects default
    [timeout_effect]. recurring=True -> self-reactivates, counts against
    proxy_recurring_aid_cap.

    effects: complete_effect/remove_effect/cancel_effect/timeout_effect.
    triggers: visible/available/activation/custom_cost_trigger.
    Stubs are placeholders for hand-filling. dry_run=True previews. Ends with
    a full contract check.
    """
    return pseudo.create(
        token=token, proxy=proxy, supporter=supporter, kind=kind,
        effects=effects, triggers=triggers, cost=cost,
        intel_base_cost=intel_base_cost, days_remove=days_remove,
        days_re_enable=days_re_enable, mission_days_timeout=mission_days_timeout,
        mission_is_good=mission_is_good, recurring=recurring,
        fire_only_once=fire_only_once, ai_will_do=ai_will_do, dry_run=dry_run,
    )


@mcp.tool()
def delete_proxy_pseudodecision(token: str, dry_run: bool = False) -> str:
    """Delete a proxy-war pseudodecision from all contract files, brace-safely.

    Removes registration (_proxy_init_ideas.txt), backing decision/mission +
    _timeout dummy (OTH_proxy_wars.txt), <token>_<suffix> effects/triggers, loc
    keys. Does NOT touch tokens.txt (append-only, dead token is harmless) and
    reports bespoke GUI/event references for hand review. dry_run=True previews.
    """
    return pseudo.delete(token, dry_run)


@mcp.tool()
def create_us_legislation(
    token: str,
    name: str | None = None,
    mission_desc: str | None = None,
    effect_tooltip: str | None = None,
    timeout_days: int = 120,
    dry_run: bool = False,
) -> str:
    """Create a US congress bill: all 5 boilerplate files at once.

    Given a token (snake_case, e.g. 'USA_clean_air_act'): registers it in
    tokens.txt (EOF), writes the four defined_texts (phase/votes/attributes/
    sponsor) + four dispatcher entries in OTH_USA_legislation_loc.txt, a
    placeholder <token>_effect, a <token>_mission decision under
    USA_congress_management, and loc keys (<token>, <token>_mission,
    <token>_mission_desc, <token>.tt).

    Default PLACEHOLDER_* prose (no-AI-writing policy); pass name/mission_desc/
    effect_tooltip only with verbatim wording. Fill <token>_effect by hand and
    paste the returned introduce-snippet into the spawning focus/event.
    dry_run=True previews without writing.
    """
    return legislation.create(
        token=token, name=name, mission_desc=mission_desc,
        effect_tooltip=effect_tooltip, timeout_days=timeout_days,
        dry_run=dry_run,
    )


@mcp.tool()
def delete_us_legislation(token: str, dry_run: bool = False) -> str:
    """Delete a US congress bill, brace-safely.

    Removes its four defined_texts + dispatcher entries (OTH_USA_legislation_loc.txt),
    <token>_effect, <token>_mission decision, and loc keys. Does NOT touch
    tokens.txt (append-only, dead token is harmless) and reports bespoke
    focus/event introduce-sites for hand review. dry_run=True previews.
    """
    return legislation.delete(token, dry_run)


def main() -> None:
    # Fail fast with a clear message if the mod path is wrong.
    config.mod_path()
    mcp.run()


if __name__ == "__main__":
    main()
