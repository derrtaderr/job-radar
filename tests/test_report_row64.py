"""Rendering a prior verdict and the non-kill flags (row 64).

The queue is the only artifact the human reads each morning, so a decision that
does not reach it has not compounded. Two surfaces:

- a **Prior** column, so a req you already judged is legible as such at the same
  glance you rank everything else at, and
- a **Flagged, not killed** section, which quotes the evidence behind every
  non-kill flag. The kills already work this way, and a flag nobody can check is
  a flag nobody can overrule.
"""
from engine.radar.ledger import Decision
from engine.radar.report import render_report
from tests.fixtures import make_report_row

DAY = "2026-09-26"

KILLED_BY_HAND = Decision(
    jid="j1", company="Northwind Analytics", title="Data Engineer",
    verdict="kill", reason="bi-analytics", date="2026-09-25",
    url="https://example.com/jobs/j1")


def _survivor(**overrides):
    row = make_report_row(prior=None, repost_of=None, notes=[])
    row.update(overrides)
    return row


def _killed(**overrides):
    row = make_report_row(flags=[("bdr-scope", "carry a quota of 30")],
                          prior=None, repost_of=None, notes=[])
    row.pop("score", None)
    row.update(overrides)
    return row


def _line_for(text, needle):
    return next(line for line in text.splitlines() if needle in line)


# --- the table ----------------------------------------------------------------

def test_the_table_has_a_prior_column_and_a_flags_column():
    header = _line_for(render_report([_survivor()], [], DAY), "| Score")
    assert "| Prior |" in header
    assert "| Flags |" in header


def test_a_judged_row_shows_its_verdict_and_reason_in_the_table():
    text = render_report([_survivor(prior=KILLED_BY_HAND)], [], DAY)
    assert "kill (bi-analytics)" in _line_for(text, "Northwind Analytics")


def test_a_repost_names_the_jid_it_may_be_a_repost_of():
    text = render_report([_survivor(repost_of="j1")], [], DAY)
    assert "possible repost of j1" in _line_for(text, "Northwind Analytics")


def test_a_noted_row_names_its_flags_in_the_table():
    text = render_report(
        [_survivor(notes=[("junior-band", "1-4 years of relevant experience")])],
        [], DAY)
    assert "junior-band" in _line_for(text, "Northwind Analytics")


def test_a_row_with_nothing_attached_renders_and_says_nothing():
    text = render_report([_survivor()], [], DAY)
    assert "possible repost" not in text
    assert "kill (" not in text


def test_a_row_predating_these_fields_still_renders():
    # make_report_row's plain shape — no prior, repost_of or notes keys at all.
    # The renderer must read them defensively, or one old caller takes the run
    # down at the last step, after the scrape has already been spent.
    text = render_report([make_report_row()], [], DAY)
    assert "Northwind Analytics" in text


# --- the quoted evidence ------------------------------------------------------

def test_the_flagged_section_quotes_the_evidence():
    text = render_report(
        [_survivor(notes=[("junior-band", "1-4 years of relevant experience")])],
        [], DAY)
    assert "## Flagged, not killed" in text
    assert '"1-4 years of relevant experience"' in text


def test_the_flagged_section_is_absent_when_nothing_is_flagged():
    text = render_report([_survivor()], [], DAY)
    assert "Flagged, not killed" not in text


def test_the_flagged_section_carries_the_prior_verdict_and_the_repost():
    text = render_report(
        [_survivor(prior=KILLED_BY_HAND, repost_of="j1")], [], DAY)
    section = text.split("## Flagged, not killed", 1)[1]
    assert "bi-analytics" in section
    assert "j1" in section


# --- kills --------------------------------------------------------------------

def test_a_killed_row_still_shows_that_it_was_judged_by_hand():
    # Worth knowing even when a rule killed it too: it says the rule is doing
    # what you wanted it to do.
    text = render_report([], [_killed(prior=KILLED_BY_HAND)], DAY)
    assert "kill (bi-analytics)" in _line_for(text, "Northwind Analytics")


def test_a_killed_row_shows_a_repost_flag():
    text = render_report([], [_killed(repost_of="j1")], DAY)
    assert "possible repost of j1" in _line_for(text, "Northwind Analytics")


def test_a_killed_row_with_nothing_attached_renders_as_before():
    text = render_report([], [_killed()], DAY)
    assert "bdr-scope" in text
    assert "possible repost" not in text


# --- the counts line ----------------------------------------------------------

def test_the_header_counts_the_rows_carrying_a_prior_verdict():
    text = render_report(
        [_survivor(prior=KILLED_BY_HAND), _survivor(jid="j2", company="Cobalt Grid")],
        [], DAY)
    assert "1 already judged" in text


def test_the_header_says_nothing_about_prior_verdicts_when_there_are_none():
    assert "already judged" not in render_report([_survivor()], [], DAY)
