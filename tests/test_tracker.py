"""Tracker suppression: what the radar already knows you're in play on.

Every fixture here is synthetic — fictional employers for the example persona
(a data engineer), fictional posting URLs under example.com. Nothing in this
file describes a real search.
"""
import datetime

from engine.radar.tracker import tracker_companies

ACTIVE = {"active", "drafted but not applied"}


def test_tracker_companies_parses_table_first_cells():
    text = (
        "## Active\n\n"
        "| Company | Role | Stage |\n|---|---|---|\n"
        "| Cobalt Grid | Data Platform Engineer | HM round |\n"
        "| Harborlight Data | Senior Data Engineer | Screen |\n\n"
        "## Drafted but not applied\n\n"
        "| Company | Role |\n|---|---|\n| Tessellate Labs | Analytics Engineer |\n")
    assert tracker_companies(text, ACTIVE) == {
        "cobalt grid", "harborlight data", "tessellate labs"}


def test_tracker_companies_ignores_prose_and_headers():
    assert tracker_companies("# My applications\n\nNo tables here.\n", ACTIVE) == set()


def test_tracker_companies_excludes_inactive_sections():
    # Only the sections you name as active suppress. A closed conversation, or a
    # lead you filed but never started, must not hide a fresh posting.
    text = (
        "## Active\n\n"
        "| Company | Role |\n|---|---|\n| Cobalt Grid | Data Engineer |\n\n"
        "## Drafted but not applied\n\n"
        "| Company | Role |\n|---|---|\n| Harborlight Data | Data Engineer |\n\n"
        "## Research (JD filed, no work started)\n\n"
        "| Company | Role |\n|---|---|\n| Pinecrest Software | Data Engineer |\n\n"
        "## Closed\n\n"
        "| Company | Role | Outcome |\n|---|---|---|\n"
        "| Meridian Rows | Data Engineer | Rejected |\n")
    got = tracker_companies(text, ACTIVE)
    assert got == {"cobalt grid", "harborlight data"}
    assert "pinecrest software" not in got and "meridian rows" not in got


def test_tracker_companies_honors_caller_supplied_sections():
    # The section names are config (settings.yaml tracker_active_sections), not
    # a constant baked into the engine — a different tracker can name them
    # anything, and matching is case-insensitive against the heading.
    text = (
        "## In flight\n\n"
        "| Company | Role |\n|---|---|\n| Cobalt Grid | Data Engineer |\n\n"
        "## Active\n\n"
        "| Company | Role |\n|---|---|\n| Harborlight Data | Data Engineer |\n")
    assert tracker_companies(text, {"in flight"}) == {"cobalt grid"}


def test_tracker_companies_skips_header_and_separator_rows():
    text = ("## Active\n\n"
            "| Company | Role |\n| :--- | ---: |\n| Cobalt Grid | Data Engineer |\n")
    assert tracker_companies(text, ACTIVE) == {"cobalt grid"}
