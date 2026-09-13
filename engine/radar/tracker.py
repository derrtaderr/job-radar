"""Tracker suppression — don't surface a company you're already talking to.

The tracker is an ordinary markdown file of `## Section` headings and pipe
tables, because the point is that a human maintains it by hand. This module
reads it and never writes it: which sections count as "in play", and how long a
closed row keeps suppressing, are both config, not engine opinions.
"""
from __future__ import annotations


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
