"""The day's delivery folder: queue.md plus a jd/ file per posting.

Every fixture here is synthetic — fictional employers for the example persona
(a data engineer), fictional posting URLs under example.com.
"""
from engine.radar.report import _comp, render_report
from tests.fixtures import make_report_row

DAY = "2026-09-13"


def test_comp_range_renders_in_thousands():
    assert _comp({"min_amount": 150000, "max_amount": 190000,
                  "interval": "yearly"}) == "$150-190K"


def test_comp_max_only():
    assert _comp({"min_amount": None, "max_amount": 190000,
                  "interval": "yearly"}) == "to $190K"


def test_comp_min_only():
    assert _comp({"min_amount": 150000, "max_amount": None,
                  "interval": "yearly"}) == "from $150K"


def test_comp_unlisted():
    assert _comp({"min_amount": None, "max_amount": None,
                  "interval": "yearly"}) == "unlisted"


def test_comp_hourly_keeps_the_interval_visible():
    # A non-yearly number must never be silently rendered as a salary band —
    # "$40-60K" for an hourly rate would be a lie the reader can't catch.
    assert _comp({"min_amount": 40, "max_amount": 60,
                  "interval": "hourly"}) == "40-60 hourly"


def test_comp_hourly_single_bound():
    assert _comp({"min_amount": None, "max_amount": 60,
                  "interval": "hourly"}) == "60 hourly"


def test_comp_hourly_unlisted():
    assert _comp({"min_amount": None, "max_amount": None,
                  "interval": "hourly"}) == "unlisted"


def test_comp_interval_absent_defaults_to_yearly_range():
    assert _comp({"min_amount": 100000, "max_amount": 150000,
                  "interval": None}) == "$100-150K"


def test_comp_drops_a_pointless_decimal_on_non_yearly_amounts():
    # Scraped amounts arrive as floats; "40.0-60.0 hourly" is noise.
    assert _comp({"min_amount": 40.0, "max_amount": 60.5,
                  "interval": "hourly"}) == "40-60.5 hourly"


# --- rendering --------------------------------------------------------------

def test_render_returns_none_when_there_is_nothing_to_say():
    # No survivors and no kills means no file — an empty queue.md is worse than
    # no queue.md, because it looks like a finished run that found nothing.
    assert render_report([], [], DAY) is None


def test_render_sorts_by_score_and_carries_frontmatter():
    out = render_report(
        [make_report_row(company="Quarry Systems", score=40),
         make_report_row(company="Cobalt Grid", score=90)], [], DAY)
    assert out.index("Cobalt Grid") < out.index("Quarry Systems")
    assert "read_by: your daily review session" in out
    assert DAY in out


def test_render_frontmatter_reader_is_generic_not_tool_specific():
    # The report is read by whoever runs the radar; it must not name one
    # person's workflow or their vault.
    out = render_report([make_report_row()], [], DAY)
    head = out.split("---")[1]
    assert "read_by:" in head
    assert "/daily" not in out and "vault" not in out.lower()


def test_render_counts_survivors_and_kills_in_the_header():
    out = render_report(
        [make_report_row()],
        [dict(make_report_row(company="Quarry Systems"),
              flags=[("bdr-scope", "carry a quota")])], DAY)
    assert "1 in the queue" in out and "1 killed by rule" in out


def test_render_killed_rows_struck_through_with_quoted_evidence():
    # A kill is never silent: the reader sees the posting, the rule that fired,
    # and the line of the posting that matched, so overruling is a one-liner.
    out = render_report([], [dict(make_report_row(company="Quarry Systems"),
                                  flags=[("bdr-scope", "carry a quota")])], DAY)
    assert "~~" in out
    assert "Quarry Systems" in out
    assert "bdr-scope" in out and "carry a quota" in out


def test_render_shows_every_flag_on_a_multi_kill_row():
    out = render_report([], [dict(make_report_row(),
                                  flags=[("bdr-scope", "carry a quota"),
                                         ("location", "Phoenix, AZ")])], DAY)
    assert "bdr-scope" in out and "location" in out and "Phoenix, AZ" in out


def test_render_missing_fields_show_empty_not_none():
    # A literal "None" in a queue cell reads as data and wastes the reader's time.
    out = render_report([make_report_row(date_posted=None, location=None,
                                         job_url=None)], [], DAY)
    assert "None" not in out


def test_render_killed_missing_job_url_shows_empty_not_none():
    out = render_report([], [dict(make_report_row(job_url=None),
                                  flags=[("bdr-scope", "carry a quota")])], DAY)
    assert "None" not in out


def test_render_escapes_pipe_in_title_and_company():
    # An unescaped pipe in a value would silently break the table columns.
    out = render_report([make_report_row(title="Data Engineer | Platform",
                                         company="Cobalt | Grid")], [], DAY)
    assert "Data Engineer \\| Platform" in out
    assert "Cobalt \\| Grid" in out
