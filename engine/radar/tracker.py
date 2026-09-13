"""Tracker suppression — don't surface a company you're already talking to.

The tracker is an ordinary markdown file of `## Section` headings and pipe
tables, because the point is that a human maintains it by hand. This module
reads it and never writes it: which sections count as "in play", and how long a
closed row keeps suppressing, are both config, not engine opinions.
"""
from __future__ import annotations

import datetime
import re


def _sections(active_sections) -> set:
    return {str(s).strip().lower() for s in (active_sections or ())}


def _first_cell(line: str):
    """The company cell of a markdown table row, or None when the line isn't a
    data row — the header row ("| Company |") and the separator ("|---|") both
    look like rows and neither names a company."""
    cells = line.split("|")
    if len(cells) < 2:
        return None
    first = cells[1].strip()
    if not first or first.lower() == "company" or set(first) <= {"-", " ", ":"}:
        return None
    return first


def _walk_sections(text: str, wanted: set):
    """Yield every table row inside a wanted section. Section membership is
    tracked by watching '## ' headings go by as we scan, which is what keeps a
    Closed row from being read as an Active one."""
    section = None
    for line in (text or "").splitlines():
        if line.startswith("## "):
            section = line[3:].strip().lower()
            continue
        if section not in wanted or not line.startswith("|"):
            continue
        yield line


def tracker_companies(text: str, active_sections) -> set:
    """Lowercased company names from the tracker sections you consider active."""
    wanted = _sections(active_sections)
    companies = set()
    for line in _walk_sections(text, wanted):
        first = _first_cell(line)
        if first:
            companies.add(first.lower())
    return companies


_POSTING_URL = re.compile(r"https?://[^\s)|]+")


def tracker_posting_urls(text: str, active_sections) -> list:
    """(company, url) for every active-section row carrying a posting URL.

    Deliberately the same sections as tracker_companies: a closed row is not a
    pending application, and re-checking its posting would produce noise about a
    job nobody is waiting on. Rows with no URL (a recruiter conversation, say)
    are skipped rather than reported — there is nothing to check.
    """
    wanted = _sections(active_sections)
    out = []
    for line in _walk_sections(text, wanted):
        first = _first_cell(line)
        if not first:
            continue
        match = _POSTING_URL.search(line)
        if match:
            # The URL usually sits in a parenthetical inside a prose cell, so
            # trailing markdown/sentence punctuation is not part of the address.
            out.append((first, match.group(0).rstrip(").,")))
    return out


_ISO_DATE = re.compile(r"\b(20\d\d-\d\d-\d\d)\b")


def closed_recent_companies(text: str, today, window_days: int) -> set:
    """Companies whose Closed row carries a close date inside the window.

    A recent close is a live conversation, not a clean slate — re-queueing a
    company you just finished with is exactly the miss this prevents. An ancient
    close is free to resurface, which is why the window is a number from config
    rather than a permanent blocklist. A row with no parseable date does NOT
    suppress: an unknown close date must never silently hide fresh postings.
    """
    companies = set()
    for line in _walk_sections(text, {"closed"}):
        first = _first_cell(line)
        if not first:
            continue
        cells = [c.strip() for c in line.split("|")]
        date_cell = cells[3] if len(cells) > 3 else ""
        # Date cells carry prose with several dates ("applied 2026-03-16, screen
        # cancelled 2026-08-20") — the latest ISO date decides recency.
        dates = _ISO_DATE.findall(date_cell)
        if not dates:
            continue
        latest = datetime.date.fromisoformat(max(dates))
        if (today - latest).days <= window_days:
            companies.add(first.lower())
    return companies


def _normalize_tracker_cell(cell: str) -> str:
    """Strip a trailing parenthetical annotation (e.g. "(via referral)") and
    surrounding whitespace, lowercased. Tracker cells carry notes a scraped
    posting never will, and those notes must not defeat a match."""
    c = (cell or "").strip()
    if c.endswith(")") and "(" in c:
        c = c[:c.rindex("(")].strip()
    return c.lower()


def tracker_suppresses(company, tracker_set) -> bool:
    """Does a scraped company name correspond to something already tracked?

    Exact matching misses real hits, because the two sides are written by
    different authors: the scrape says "Harborlight Data, Inc." where the
    tracker says "Harborlight Data (via referral)". So normalize both sides and
    match by substring in either direction — with a floor of 4 characters on the
    shorter string, so a two-letter cell can't degenerate into matching
    everything.
    """
    c = (company or "").strip().lower()
    if not c:
        return False
    for t in tracker_set:
        tn = _normalize_tracker_cell(t)
        if not tn or min(len(tn), len(c)) < 4:
            continue
        if tn in c or c in tn:
            return True
    return False
