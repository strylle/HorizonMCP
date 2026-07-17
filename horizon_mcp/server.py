"""
HorizonMCP server
"""

# docustrings are LLM generated as it's the AI using it anyway

from __future__ import annotations
from mcp.server.fastmcp import FastMCP
from .core import config, pdx
from .tools import blocks, events, gfx, legislation, lint, pseudo, tokens, varflow

mcp = FastMCP("horizon-mcp")


@mcp.tool()
def list_event_namespaces() -> str:
    """List every event namespace declared in the mod and which file declares it.

    Cheap way to see valid namespaces before creating an event.
    """
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
    """Create a HOI4 event in othmod: writes the script block AND its localisation.

    The event id is auto-assigned (next free in the namespace).

    By default (placeholder_loc=True) no prose is written by this tool - title,
    desc, and option button text are all generic PLACEHOLDER_* strings meant to
    be filled in by hand (no-AI-writing policy for loc). Pass
    placeholder_loc=False plus explicit title/desc/option.name only when the
    exact wording has been supplied verbatim and should be written as-is.

    Set dry_run=True first to preview the exact script + loc that would be written
    without changing any files. For a NEW namespace, pass target_file (the events
    file to create/append to).
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
    """Fix "dynamic token can cause OOS" warnings by registering the tokens.

    Pass `text` to scan a pasted warning or log snippet verbatim, e.g.:
    'token operation_steal_tech_airforce_cost is a dynamic token, this can
    cause OOS depending on how it's used, please add it as a synchronized
    dynamic token to prevent OOS's'

    Omit `text` to instead scan the game's error.log file (defaults to the
    standard macOS Paradox log path
    ~/Documents/Paradox Interactive/Hearts of Iron IV/logs/error.log, or set
    LOG_PATH / pass log_path to point elsewhere).

    Either way, extracts every distinct token found and appends new ones to
    common/synchronized_dynamic_tokens/tokens.txt (no-op for tokens already
    registered).
    """
    return tokens.fix_all(text=text, log_path=log_path)


@mcp.tool()
def check_gfx_references(file: str | None = None) -> str:
    """Verify every GFX_ sprite reference resolves to a defined sprite.

    Indexes sprite definitions from the mod's .gfx files plus vanilla HOI4's
    (GAME_PATH, defaulting to the standard Steam install). Pass `file` as a
    mod-relative path (e.g. 'interface/OTH/OTH_proxy_screen.gui') to check one
    file, or omit it to sweep every .gui file and scripted_guis script.

    Bracket-substituted names like GFX_foo_[ROOT.GetTag] can't be fully
    resolved statically; for those it reports which concrete variants exist
    (or flags the prefix if none do).
    """
    if file:
        return gfx.check_file(file)
    return gfx.check_all()


@mcp.tool()
def validate_braces(file: str | None = None) -> str:
    """Check brace balance in mod script files (comments excluded from counts).

    Pass a mod-relative path to check one file, or omit to sweep every .txt/.gui/.gfx
    under common/, events/, and interface/. Run after any hand edit or block removal.
    """
    if file:
        return blocks.validate_file(file)
    return blocks.validate_all()


@mcp.tool()
def remove_named_block(file: str, name: str, dry_run: bool = False) -> str:
    """Remove one named block from a Paradox script/gui file, brace-safely.

    `name` matches either a gui element (the block containing `name = "<name>"`)
    or a script definition (`<name> = {` header). Refuses to act if the name is
    ambiguous or the file is unbalanced. Set dry_run=True to preview the removal
    (line range + first lines of the block) without writing.
    """
    return blocks.remove_block(file, name, dry_run)


@mcp.tool()
def check_variable_flow(prefix: str | None = None) -> str:
    """Cross-reference every dynamic variable/array write against its reads.

    Reports WRITE-ONLY variables (computed but never consumed - dead data) and
    READ-ONLY variables (consumed but never fed - a system silently running on
    nothing). Scans common/, events/, and localisation reads ([?var]).

    Pass `prefix` (e.g. 'OTH_proxy') to filter the report to one system's
    variables; omit it for a full sweep (noisier). Lexical analysis - loop
    value-vars and meta_effect-composed names can be false positives, so treat
    findings as leads, not verdicts.
    """
    return varflow.check_flow(prefix)


@mcp.tool()
def check_tokens_append_only() -> str:
    """Verify tokens.txt only changed by EOF appends since git HEAD.

    synchronized_dynamic_tokens/tokens.txt is positional across MP clients:
    reordering, mid-file inserts, or deletions shift token ids and cause OOS.
    Run before committing any change that touches it.
    """
    return tokens.verify_append_only()


@mcp.tool()
def add_synchronized_token(token: str) -> str:
    """Append a token to synchronized_dynamic_tokens/tokens.txt (EOF, the only safe place).

    No-op if the token is already registered. Use this instead of hand-editing
    the file - mid-file inserts cause OOS in multiplayer.
    """
    added = tokens.add_synchronized_token(token)
    if added:
        return f"Added '{token}' at EOF of synchronized_dynamic_tokens/tokens.txt"
    return f"'{token}' is already registered, no change made."


@mcp.tool()
def lint_trigger_contexts(file: str | None = None) -> str:
    """Lint trigger contexts for effect statements and unguarded division.

    Scripted-GUI `triggers`/`visible` blocks and everything under
    common/scripted_triggers are trigger contexts: persistent-state effects and
    loop effects there are silently ignored or misbehave. Also flags
    divide_[temp_]variable by a dynamic variable with no nearby zero/exists
    guard (per-frame 'divide by zero' log spam in GUI contexts).

    Pass a mod-relative file path to lint one file, or omit to sweep
    scripted_guis + scripted_triggers. Temp-variable math is tolerated.
    """
    return lint.lint(file)


@mcp.tool()
def check_pseudodecisions() -> str:
    """Verify every pseudodecision registration's six-file contract is intact.

    For each OTH_init_proxy_pseudodecision call in common/ideas it checks:
    token registered in tokens.txt; every effects/triggers token has its
    <token>_<suffix> scripted effect/trigger; a backing decision <token> and
    dummy mission <token>_timeout exist in common/decisions (mission-type
    pseudodecisions are exempt from the dummy); loc keys <token> and
    <token>_desc exist. Every missing leg fails silently in-game, so run this
    after adding or renaming any pseudodecision.
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
    """Create a proxy-war pseudodecision: all six contract files of boilerplate at once.

    Writes the registration under `supporter`'s block inside `proxy`'s on_add in
    _proxy_init_ideas.txt, the backing decision (+ _timeout dummy) or backing
    mission in OTH_proxy_wars.txt, payload/trigger stubs, PLACEHOLDER loc keys
    (<token> and <token>_desc - no-AI-prose policy), and registers the token at
    EOF of synchronized tokens.txt.

    kind='decision': uses days_remove/days_re_enable; pass cost (political
    power) OR intel_base_cost (wires the full 4-piece intel-cost contract:
    custom_cost_trigger, OTH_intel_cost text + dummy decision, and the
    OTH_spend_intel_currency block in complete_effect).
    kind='mission': uses mission_days_timeout/mission_is_good; effects default
    to [timeout_effect]. recurring=True makes it self-reactivate in
    timeout_effect and count against the country's proxy_recurring_aid_cap.

    effects from: complete_effect, remove_effect, cancel_effect, timeout_effect.
    triggers from: visible, available, activation, custom_cost_trigger.
    Payload/trigger stubs are placeholders to fill in by hand. Set dry_run=True
    to preview everything without writing. Ends with a full contract check.
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
    """Delete a proxy-war pseudodecision from all its contract files, brace-safely.

    Removes its registration block from _proxy_init_ideas.txt, its backing
    decision/mission and _timeout dummy from OTH_proxy_wars.txt, every
    <token>_<suffix> payload effect and trigger, and its loc keys. Deliberately
    does NOT touch tokens.txt (positional/append-only - removing lines causes
    OOS; a dead token is harmless) and does not hunt bespoke references in
    GUIs/events - those are reported for hand review. Set dry_run=True to preview.
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
    """Create a US congress legislation (bill) entry: all 5 files of boilerplate at once.

    Given a bill token (lowercase snake_case, e.g. 'USA_clean_air_act') this
    registers the token in tokens.txt (EOF append), writes the four per-bill
    defined_texts (phase/votes/attributes/sponsor) plus the four dispatcher
    entries in OTH_USA_legislation_loc.txt, a placeholder <token>_effect in
    the legislation scripted effects, a <token>_mission decision under
    USA_congress_management, and the loc keys (<token>, <token>_mission,
    <token>_mission_desc with the standard stage/votes/sponsor block,
    <token>.tt).

    By default all prose is PLACEHOLDER_* (no-AI-writing policy for loc);
    pass name / mission_desc / effect_tooltip only with wording supplied
    verbatim. The bill's actual passage effect must be filled in by hand in
    <token>_effect, and the returned introduce-snippet pasted into whatever
    focus/event spawns the bill. Set dry_run=True to preview everything
    without writing.
    """
    return legislation.create(
        token=token, name=name, mission_desc=mission_desc,
        effect_tooltip=effect_tooltip, timeout_days=timeout_days,
        dry_run=dry_run,
    )


@mcp.tool()
def delete_us_legislation(token: str, dry_run: bool = False) -> str:
    """Delete a US congress legislation (bill) entry, brace-safely.

    Removes the bill's four defined_texts and its dispatcher entries from
    OTH_USA_legislation_loc.txt, its <token>_effect scripted effect, its
    <token>_mission decision, and its loc keys. Deliberately does NOT touch
    tokens.txt (positional/append-only - removing lines causes OOS; a dead
    token is harmless) and does not hunt down bespoke introduce-sites in
    focuses/events - those are reported for hand review. Set dry_run=True
    to preview.
    """
    return legislation.delete(token, dry_run)


def main() -> None:
    # Fail fast with a clear message if the mod path is wrong.
    config.mod_path()
    mcp.run()


if __name__ == "__main__":
    main()
