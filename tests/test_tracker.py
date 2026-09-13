"""Tracker suppression: what the radar already knows you're in play on.

Every fixture here is synthetic — fictional employers for the example persona
(a data engineer), fictional posting URLs under example.com. Nothing in this
file describes a real search.
"""
import datetime

from engine.radar.tracker import (
    closed_recent_companies,
    tracker_companies,
    tracker_suppresses,
)

ACTIVE = {"active", "drafted but not applied"}
TODAY = datetime.date(2026, 9, 13)
WINDOW = 90


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


# --- closed-row recency -----------------------------------------------------

def test_closed_recent_companies_suppress_within_window():
    # A company you closed with six weeks ago is a live conversation, not a
    # clean slate. A close from five months ago is free to resurface.
    text = (
        "## Closed\n\n"
        "| Company | Role | Date closed | Outcome |\n|---|---|---|---|\n"
        "| Cobalt Grid | Data Platform Engineer | 2026-08-01 | Closed |\n"
        "| Harborlight Data | Analytics Engineer | 2026-04-12 | Closed-lost |\n")
    got = closed_recent_companies(text, TODAY, WINDOW)
    assert "cobalt grid" in got          # 43 days ago — suppressed
    assert "harborlight data" not in got  # 154 days ago — free to resurface


def test_closed_recent_companies_uses_latest_date_in_cell():
    # Date-closed cells carry prose with several dates — the LATEST ISO date
    # decides recency, not the first one written.
    text = (
        "## Closed\n\n"
        "| Company | Role | Date closed | Outcome |\n|---|---|---|---|\n"
        "| Tessellate Labs | Data Engineer "
        "| applied 2026-03-16, screen cancelled 2026-08-20 | Closed |\n")
    assert "tessellate labs" in closed_recent_companies(text, TODAY, WINDOW)


def test_closed_row_without_parseable_date_does_not_suppress():
    # An unknown close date must never silently hide fresh postings.
    text = (
        "## Closed\n\n"
        "| Company | Role | Date closed | Outcome |\n|---|---|---|---|\n"
        "| Pinecrest Software | Data Engineer | **TBD** | TBD |\n")
    assert closed_recent_companies(text, TODAY, WINDOW) == set()


def test_closed_recent_ignores_other_sections():
    # An active row's dates must not leak into the closed-recency set.
    text = (
        "## Active\n\n"
        "| Company | Role | Source | Stage |\n|---|---|---|---|\n"
        "| Meridian Rows | Data Engineer | applied 2026-09-07 | Applied |\n")
    assert closed_recent_companies(text, TODAY, WINDOW) == set()


def test_closed_window_is_a_parameter_not_a_constant():
    text = (
        "## Closed\n\n"
        "| Company | Role | Date closed | Outcome |\n|---|---|---|---|\n"
        "| Cobalt Grid | Data Engineer | 2026-08-01 | Closed |\n")
    assert closed_recent_companies(text, TODAY, 90) == {"cobalt grid"}
    assert closed_recent_companies(text, TODAY, 30) == set()


def test_closed_row_dated_exactly_on_the_window_edge_still_suppresses():
    text = (
        "## Closed\n\n"
        "| Company | Role | Date closed | Outcome |\n|---|---|---|---|\n"
        "| Cobalt Grid | Data Engineer | 2026-06-15 | Closed |\n")
    assert closed_recent_companies(text, TODAY, 90) == {"cobalt grid"}


# --- name matching ----------------------------------------------------------

def test_tracker_suppresses_normalized_annotation():
    # A tracker cell carries notes the scrape never will.
    assert tracker_suppresses("Cobalt Grid", {"cobalt grid (via referral)"})


def test_tracker_suppresses_substring_either_direction():
    assert tracker_suppresses("Harborlight Data, Inc.", {"harborlight data"})
    assert tracker_suppresses("Tessellate", {"tessellate labs"})


def test_tracker_suppresses_is_case_insensitive():
    assert tracker_suppresses("PINECREST SOFTWARE", {"Pinecrest Software"})


def test_tracker_suppresses_ignores_short_cells():
    # A two-character tracker cell must not cause degenerate substring matches.
    assert not tracker_suppresses("Meridian Rows", {"me"})


def test_tracker_suppresses_rejects_unrelated_and_empty_names():
    assert not tracker_suppresses("Quarry Systems", {"cobalt grid"})
    assert not tracker_suppresses("", {"cobalt grid"})
    assert not tracker_suppresses(None, {"cobalt grid"})
    assert not tracker_suppresses("Cobalt Grid", set())
