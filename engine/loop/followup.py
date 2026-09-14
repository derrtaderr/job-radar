"""Followup — staleness scan over a tracker's Active section.

A row is "stale" when the LATEST ISO date found in its Last-touch cell is
`days` or more days before `today` (exactly `days` counts — inclusive, not
"more than"). Last-touch cells routinely carry an annotation around the
date ("2026-09-12 (sent reply)") or, less often, more than one date in the
same cell; either way the rule is the same one tracker_schema.py already
uses elsewhere: the latest ISO-date match (YYYY-MM-DD) wins.

A row whose Last-touch cell is empty, or non-empty but carries no
parseable ISO date at all, is never silently dropped — it can't be judged
stale or fresh, so it goes into a second bucket (`unknown_touch`) the
caller is expected to surface, not swallow. The same holds for a Last-touch
date that falls AFTER today (a typo'd year is the realistic cause,
e.g. 2027 instead of 2026): that produces a negative days_quiet, which is
exactly as unjudgeable as no date at all, so it also routes to
unknown_touch rather than silently failing the `>= days` test and
vanishing from both buckets.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from engine.loop.tracker_schema import parse_tracker

_ISO_DATE = re.compile(r"\b20\d\d-\d\d-\d\d\b")


@dataclass
class StaleRow:
    company: str
    role: str
    last_touch: date
    days_quiet: int
    stage: str
    next_step: str


def _latest_date(cell: str):
    """Return the latest ISO date in `cell` as a date, or None if the cell
    carries no parseable ISO date at all."""
    matches = _ISO_DATE.findall(cell)
    if not matches:
        return None
    return max(datetime.strptime(m, "%Y-%m-%d").date() for m in matches)


def stale_active(text: str, today: date, days: int):
    """Scan the tracker's Active section for rows gone quiet.

    Returns (stale, unknown_touch):
      - stale: list[StaleRow], one per Active row whose latest Last-touch
        date is `days` or more days before `today`, in the row's original
        tracker order.
      - unknown_touch: list[(Row, reason)] for every Active row whose
        Last-touch cell is empty, has no parseable ISO date, or parses to
        a date AFTER `today` (days_quiet would be negative — treated as a
        likely typo'd year, not a valid touch date). `reason` is a
        plain-English string naming what was wrong; `Row` is the same
        header-keyed object parse_tracker produces, so a caller can still
        read Company/Role/etc off it.

    A tracker with no Active section (or empty text) returns ([], []) —
    nothing to report is not an error.
    """
    sections = parse_tracker(text or "")
    table = sections.get("active")

    stale: list = []
    unknown_touch: list = []
    if table is None:
        return stale, unknown_touch

    for row in table.rows:
        cell = (row.get("Last touch") or "").strip()
        if not cell:
            unknown_touch.append((row, "empty Last touch"))
            continue

        latest = _latest_date(cell)
        if latest is None:
            unknown_touch.append((row, f"no parseable date in Last touch {cell!r}"))
            continue

        days_quiet = (today - latest).days
        if days_quiet < 0:
            unknown_touch.append((row, (
                f"Last touch is in the future ({latest.isoformat()}) — "
                "check for a typo'd year")))
            continue

        if days_quiet >= days:
            stale.append(StaleRow(
                company=row.get("Company") or "",
                role=row.get("Role") or "",
                last_touch=latest,
                days_quiet=days_quiet,
                stage=row.get("Stage") or "",
                next_step=row.get("Next step") or "",
            ))

    return stale, unknown_touch
