"""The order of steps, as code.

A referral usually has to land before the application: many employers do not
credit one once the candidate is already in their applicant system. So when
the person knows someone at the company, applying is held until they have
asked, for at most three business days. Postings fill, and a referral ask
must never hold a good one hostage.

`due` is the reader that keeps all of this off the person's memory. Their
daily brief calls it.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, replace

from engine.network.company import canonical
from engine.network.dates import add_business_days
from engine.network.touches import latest_by_person

WARM_WAIT_BUSINESS_DAYS = 3
NO_REPLY_AFTER_BUSINESS_DAYS = 10
# An override or an application speaks for the posting it was made about. A
# company keeps hiring, so after this long it no longer waves through a new
# posting there: the person decides again, with the gate in front of them.
DECISION_FRESH_DAYS = 90
# A reply is not a referral. "Sure, send me your resume" still has to become
# a submitted referral before the application, so a reply holds the gate.
_GIVEN_UP_STATES = ("declined", "no_reply", "left_company")


@dataclass(frozen=True)
class GateResult:
    code: int  # 0 proceed, 3 ask first, 4 an ask is inside its window
    message: str


@dataclass(frozen=True)
class DueItem:
    since: str
    company: str
    message: str


def _iso(text: str) -> datetime.date:
    return datetime.date.fromisoformat(text)


def gate(report, touches, aliases, today: datetime.date) -> GateResult:
    """Should /apply proceed for this company today?"""
    company = report.company
    warm = [p for p in report.paths if p.kind == "warm"]
    if not warm:
        return GateResult(0, f"{company}: no warm path, apply as usual")

    key = canonical(company, aliases)
    mine = [t for t in touches if canonical(t.company, aliases) == key]
    recent = {t.state for t in mine
              if (today - _iso(t.date)).days <= DECISION_FRESH_DAYS}
    if "override" in recent:
        return GateResult(0, f"{company}: override recorded, proceed")
    if "applied" in recent:
        return GateResult(0, f"{company}: already applied")

    by_slug = {p.slug: p for p in warm}
    latest = latest_by_person(mine, aliases)
    warm_latest = [t for (_, slug), t in latest.items() if slug in by_slug]
    referred = [t for t in warm_latest if t.state == "referred"]
    if referred:
        name = by_slug[referred[0].person_slug].name
        return GateResult(0, f"{company}: {name} referred you. Apply through "
                             "their referral link, or confirm they submitted you")
    asks = [t for t in mine if t.state == "asked" and t.person_slug in by_slug]
    if not asks:
        best = warm[0]
        return GateResult(3, (
            f"{company}: you know {best.name} ({best.detail or 'no title'}, "
            f"connected {best.since or 'date unknown'}). Ask them before applying, "
            "because a referral usually has to land before the application: "
            "run /reach. To apply anyway, record it first: "
            f'network_cli.py touch --company "{company}" --state override'))
    given_up = [t for t in warm_latest if t.state in _GIVEN_UP_STATES]
    if given_up and len(given_up) == len(warm_latest):
        return GateResult(0, f"{company}: every warm ask is closed "
                             f"({', '.join(sorted({t.state for t in given_up}))}). "
                             "Apply now and send the hiring-manager note")

    replies = [t for t in warm_latest if t.state == "replied"]
    if replies:
        last_reply = max(replies, key=lambda t: t.date)
        expiry = add_business_days(_iso(last_reply.date), WARM_WAIT_BUSINESS_DAYS)
        name = by_slug[last_reply.person_slug].name
        if today < expiry:
            return GateResult(4, (
                f"{company}: {name} replied on {last_reply.date}, but a reply is not "
                "a referral. Wait for them to submit you, then record it with "
                f"`reply --state referred`, or apply without them after "
                f"{expiry.isoformat()}"))
        return GateResult(0, f"{company}: {name} replied on {last_reply.date} but no "
                             f"referral was confirmed by {expiry.isoformat()}. Apply "
                             "now, tell them you did, and send the hiring-manager note")

    last = max(asks, key=lambda t: t.date)
    expiry = add_business_days(_iso(last.date), WARM_WAIT_BUSINESS_DAYS)
    name = by_slug[last.person_slug].name
    if today < expiry:
        return GateResult(4, f"{company}: asked {name} on {last.date}; wait until "
                             f"{expiry.isoformat()} before applying without them")
    return GateResult(0, f"{company}: the ask to {name} passed its window on "
                         f"{expiry.isoformat()}. Apply now and send the "
                         "hiring-manager note")


def due(touches, reports: dict, aliases, today: datetime.date) -> tuple:
    """(items, no_reply_rows). Items sort oldest first. The no_reply rows are
    the caller's to append; this function writes nothing."""
    items, no_reply = [], []
    latest = latest_by_person(touches, aliases)
    decided = {}  # canonical company -> newest applied/override date
    for t in touches:
        if t.state in ("applied", "override"):
            key = canonical(t.company, aliases)
            decided[key] = max(decided.get(key, ""), t.date)
    for (company_key, slug), t in latest.items():
        if t.state != "asked" or not slug:
            continue
        sent = _iso(t.date)
        if add_business_days(sent, NO_REPLY_AFTER_BUSINESS_DAYS) <= today:
            no_reply.append(replace(t, date=today.isoformat(), state="no_reply",
                                    note="auto: 10 business days quiet"))
            items.append(DueItem(t.date, t.company,
                                 f"{t.company}: no reply from {slug} in 10 business "
                                 "days, marked no_reply"))
        elif t.path == "warm" and decided.get(company_key, "") >= t.date:
            continue  # they already applied or overrode; "apply today" would be wrong
        elif t.path == "warm" and add_business_days(
                sent, WARM_WAIT_BUSINESS_DAYS) <= today:
            items.append(DueItem(t.date, t.company,
                                 f"{t.company}: the ask to {slug} has had 3 business "
                                 "days. Apply today and add the hiring-manager note"))
        elif t.path == "recent_hire":
            items.append(DueItem(t.date, t.company,
                                 f"{t.company}: chat ask to {slug} waiting since {t.date}"))

    for t in touches:
        if t.state != "applied":
            continue
        key = canonical(t.company, aliases)
        report = reports.get(key)
        if report is None:
            continue
        sent_hm = {s.person_slug for s in touches
                   if canonical(s.company, aliases) == key
                   and s.path == "cold_hm" and s.state == "asked"}
        for p in report.paths:
            if p.kind == "cold_hm" and p.slug not in sent_hm:
                items.append(DueItem(t.date, t.company,
                                     f"{t.company}: hiring-manager note owed to "
                                     f"{p.name} (applied {t.date})"))
    items.sort(key=lambda i: i.since)
    return items, no_reply
