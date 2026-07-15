"""Event builder!
"""

from __future__ import annotations

import string
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field

from ..core import pdx


class EventOption(BaseModel):
    name: str | None = Field(
        default=None,
        description="Options shown to the player",
    )
    effect: str | None = Field(
        default=None,
        description="event effects when picked, e.g. 'add_political_power = 50'. "
        "may be multiple lines or nested in code",
    )
    follow_up: str | None = Field(
        default=None,
        description="Event id to fire next, e.g. 'usa_flavor.13'",
    )
    tooltip: str | None = Field(
        default=None, description="Optional tooltip (preferred formatting: namespace.(int).tt )."
    )


@dataclass
class EventResult:
    event_id: str
    event_file: Path
    loc_file: Path
    block: str
    loc_entries: list[tuple[str, str]]
    namespace_added: bool
    dry_run: bool
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if self.dry_run:
            action = "Would create"
        else:
            action = "Created"
        lines = [
            f"{action} event {self.event_id}",
            f"  script -> {self.event_file}",
            f"  loc    -> {self.loc_file} ({len(self.loc_entries)} keys)",
        ]
        if self.namespace_added:
            lines.append(f"  + added 'add_namespace = {self.event_id.split('.')[0]}'")
        for w in self.warnings:
            lines.append(f"  ! {w}")
        if self.dry_run:
            lines.append("\n--- script block ---\n" + self.block)
            lines.append("\n--- loc entries ---")
            lines += [f' {k}:0 "{v}"' for k, v in self.loc_entries]
        return "\n".join(lines)


def _build_block(
    event_id: str,
    event_type: str,
    ns: str,
    n: int,
    picture: str | None,
    is_triggered_only: bool,
    trigger: str | None,
    mean_time_to_happen: str | None,
    options: list[EventOption],
) -> str:
    if event_type == "news":
        kind = "news_event"
    else:
        kind = "country_event"
    lines = []
    lines.append(f"{kind} = {{")
    lines.append(f"\tid = {event_id}")
    lines.append(f"\ttitle = {ns}.{n}.t")
    lines.append(f"\tdesc = {ns}.{n}.d")
    if picture:
        lines.append(f"\tpicture = {picture}")
    lines.append("")
    if is_triggered_only:
        lines.append("\tis_triggered_only = yes")
    if trigger:
        lines.append("\ttrigger = {")
        lines += [f"\t\t{ln}" for ln in trigger.strip().splitlines()]
        lines.append("\t}")
    if mean_time_to_happen:
        lines.append("\tmean_time_to_happen = {")
        lines += [f"\t\t{ln}" for ln in mean_time_to_happen.strip().splitlines()]
        lines.append("\t}")
    lines.append("")

    letters = string.ascii_lowercase
    for i, opt in enumerate(options):
        letter = letters[i]
        lines.append("\toption = {")
        lines.append(f"\t\tname = {ns}.{n}.{letter}")
        if opt.effect:
            lines += [f"\t\t{ln}" for ln in opt.effect.strip().splitlines()]
        if opt.follow_up:
            lines.append(f"\t\tcountry_event = {opt.follow_up}")
        lines.append("\t}")
    lines.append("}")
    return "\n".join(lines)


def create_event(
    namespace: str,
    options: list[EventOption],
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
) -> EventResult:
    """Create one event + generic localisation.
    """
    warnings: list[str] = []

    if not placeholder_loc:
        if title is None or desc is None:
            raise ValueError("placeholder_loc=False requires title and desc")
        if any(opt.name is None for opt in options):
            raise ValueError("placeholder_loc=False requires every option to be named")

    ns_map = pdx.index_event_namespaces()
    if namespace in ns_map:
        event_file = ns_map[namespace]
        if target_file and Path(target_file).name != event_file.name:
            warnings.append(
                f"namespace '{namespace}' already lives in {event_file.name}; "
                f"ignoring target_file={target_file}"
            )
    else:
        if not target_file:
            raise ValueError(
                f"Namespace '{namespace}' does not exist! Please create it"
            )
        from ..core import config
        event_file = config.events_dir() / Path(target_file).name

    if not options:
        raise ValueError("An event needs at least one option")
    if len(options) > 26:
        raise ValueError("More than 26 options is not supported")
    if len(options) > 4:
        warnings.append(
            f"{len(options)} options is a lot for one event window... it may not render well"
        )

    n = pdx.find_next_event_id(event_file, namespace) if event_file.exists() else 1
    event_id = f"{namespace}.{n}"

    block = _build_block(
        event_id, event_type, namespace, n, picture, is_triggered_only,
        trigger, mean_time_to_happen, options,
    )

    if placeholder_loc:
        title_text = "PLACEHOLDER_TITLE"
        desc_text = "PLACEHOLDER_DESC"
    else:
        title_text = title
        desc_text = desc
    loc_entries: list[tuple[str, str]] = [
        (f"{namespace}.{n}.t", title_text),
        (f"{namespace}.{n}.d", desc_text),
    ]
    letters = string.ascii_lowercase
    for i, opt in enumerate(options):
        letter = letters[i]
        name_text = f"PLACEHOLDER_OPTION_{letter.upper()}" if placeholder_loc else opt.name
        loc_entries.append((f"{namespace}.{n}.{letter}", name_text))
        if opt.tooltip:
            loc_entries.append((f"{namespace}.{n}.{letter}.tt", opt.tooltip))

    # Resolve loc file.
    from ..core import config
    if loc_file:
        loc_target = config.loc_dir() / Path(loc_file).name
    else:
        found = pdx.find_loc_file_for_namespace(namespace)
        if found:
            loc_target = found
        else:
            loc_target = config.loc_dir() / f"OTH_{namespace}_l_english.yml"
            warnings.append(
                f"no existing loc for '{namespace}'; will use {loc_target.name}"
            )

    namespace_added = False
    if not dry_run:
        if not event_file.exists():
            event_file.write_text("", encoding="utf-8")
        namespace_added = pdx.insert_namespace_declaration(event_file, namespace)
        pdx.append_script_block(event_file, block)
        pdx.append_loc_entries(loc_target, loc_entries)
    else:
        namespace_added = namespace not in ns_map

    return EventResult(
        event_id=event_id,
        event_file=event_file,
        loc_file=loc_target,
        block=block,
        loc_entries=loc_entries,
        namespace_added=namespace_added,
        dry_run=dry_run,
        warnings=warnings,
    )
