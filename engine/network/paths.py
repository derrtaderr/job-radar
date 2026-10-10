"""Who can the person reach at this company, best first.

A pure function of the network and the date. It never changes a score: a
connection does not make a posting worth pursuing, it changes the order of
steps for a posting already chosen (see the spec). The report keeps `none`
("looked, nobody") apart from `unresearched` ("never looked"), because an
empty cell that means both reads as an answer when nobody asked.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Optional

from engine.network.company import canonical, match, slugify

KINDS = ("warm", "recent_hire", "cold_hm")
STALE_AFTER_DAYS = 30
MAX_CHECKS_SHOWN = 3


@dataclass(frozen=True)
class ContactPath:
    kind: str
    slug: str
    name: str
    detail: str
    since: str


@dataclass(frozen=True)
class PathReport:
    company: str
    paths: tuple
    checks: tuple
    status: str  # found | none | unresearched
    looked_up: Optional[datetime.date]
    stale: bool
    export_date: Optional[datetime.date]


def resolve_paths(company, network, today: datetime.date) -> PathReport:
    warm, checks = [], []
    company_key = canonical(company, network.aliases)
    for c in network.connections:
        grade = match(c.company, company, network.aliases)
        if grade == "exact" and (company_key, slugify(c.name)) in network.left:
            continue
        if grade == "exact":
            warm.append(ContactPath("warm", slugify(c.name), c.name, c.position,
                                    c.connected_on))
        elif grade == "partial":
            checks.append(f"{c.name} at {c.company}")

    pf = network.people.get(company_key)
    clay = []
    if pf is not None:
        for p in pf.people:
            if p.status != "current":
                continue
            kind = "recent_hire" if p.role == "recent_hire" else "cold_hm"
            clay.append(ContactPath(kind, p.slug, p.name, p.title, p.started))

    paths = sorted(warm + clay, key=lambda p: KINDS.index(p.kind))
    if paths:
        status = "found"
    else:
        status = "none" if pf is not None else "unresearched"
    stale = pf is not None and (today - pf.looked_up).days > STALE_AFTER_DAYS
    return PathReport(company=str(company or ""), paths=tuple(paths),
                      checks=tuple(checks), status=status,
                      looked_up=pf.looked_up if pf is not None else None,
                      stale=stale, export_date=network.export_date)


def render_path_cell(report: PathReport) -> str:
    if report.status == "found":
        best = report.paths[0]
        text = f"{best.kind}: {best.name}"
        if best.kind == "warm" and best.since[:4].isdigit():
            text += f", connected {best.since[:4]}"
        if len(report.paths) > 1:
            text += f" (+{len(report.paths) - 1})"
    elif report.status == "none":
        text = f"none (looked up {report.looked_up.isoformat()})"
    else:
        text = "unresearched"
    if report.stale:
        text += " [stale]"
    if report.checks:
        shown = ", ".join(f"{c}?" for c in report.checks[:MAX_CHECKS_SHOWN])
        more = len(report.checks) - MAX_CHECKS_SHOWN
        text += f"; check: {shown}" + (f" (+{more} more)" if more > 0 else "")
    return text
