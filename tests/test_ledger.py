"""The decision ledger — the human's judgment, made machine-readable.

The miss this closes: a req read and killed by hand came back days later as the
top-scored row, because the kill had been written as prose in a markdown tracker
nothing parses. Third re-surface of that kind in four days.

The hard part is matching, and it is hard for a reason established by the live
case: the req came back under a NEW posting id. Same company, same title, same
body, a new id because the board reissued it. So matching runs three tiers —
exact jid, then the normalised (company, title) pair, then the body fingerprint
via the earlier jid's state entry — and a ledger row therefore has to carry
company and title even when it was written by jid alone.

Every company, title and posting here is invented.
"""
import datetime

from engine.radar.fingerprint import fp_body, fp_comp
from engine.radar.ledger import (
    Decision,
    append_decision,
    load_ledger,
    parse_ledger,
    prior_verdict,
)
from engine.radar.state import make_entry

HEADER = "jid,company,title,verdict,reason,date,url"

VALID = HEADER + "\n" + "\n".join([
    "j1,Northwind Analytics,Data Engineer,kill,bi-analytics,2026-09-20,https://example.com/j1",
    "j2,Cobalt Grid,Data Platform Engineer,draft,strong-fit,2026-09-21,https://example.com/j2",
]) + "\n"


def _row(**overrides):
    row = {"id": "j9", "company": "Northwind Analytics", "title": "Data Engineer",
           "description": "Northwind Analytics is hiring. Own the reporting stack. "
                          "We offer medical, dental and a 401k match.",
           "location": "Denver, CO", "is_remote": False,
           "min_amount": 150000, "max_amount": 180000, "interval": "yearly"}
    row.update(overrides)
    return row


# --- parsing ------------------------------------------------------------------

def test_parse_reads_every_column_of_every_row():
    decisions, problems = parse_ledger(VALID)
    assert problems == []
    assert [d.jid for d in decisions] == ["j1", "j2"]
    first = decisions[0]
    assert first.company == "Northwind Analytics"
    assert first.title == "Data Engineer"
    assert first.verdict == "kill"
    assert first.reason == "bi-analytics"
    assert first.date == "2026-09-20"
    assert first.url == "https://example.com/j1"


def test_parse_skips_comment_lines():
    # Same convention as exclusions.txt, and it is what lets the shipped
    # config.example ledger explain what it is to whoever opens it.
    text = ("# my judgment, one row per decision\n" + HEADER + "\n"
            "# the row below was a BI/analytics req, not an engineering one\n"
            "j1,Northwind Analytics,Data Engineer,kill,bi-analytics,2026-09-20,\n")
    decisions, problems = parse_ledger(text)
    assert problems == []
    assert [d.jid for d in decisions] == ["j1"]


def test_parse_names_a_missing_required_column():
    text = "jid,company,title,verdict\nj1,Northwind Analytics,Data Engineer,kill\n"
    decisions, problems = parse_ledger(text)
    assert decisions == []
    assert len(problems) == 1
    assert "reason" in problems[0] and "date" in problems[0] and "url" in problems[0]


def test_parse_rejects_an_unknown_verdict_by_name():
    # The enum is closed on purpose. A typo'd verdict silently ignored would
    # look exactly like a decision that was never recorded.
    text = HEADER + "\nj1,Northwind Analytics,Data Engineer,maybe,unsure,2026-09-20,\n"
    decisions, problems = parse_ledger(text)
    assert decisions == []
    assert len(problems) == 1
    assert "maybe" in problems[0]
    assert "kill" in problems[0] and "draft" in problems[0]


def test_parse_rejects_a_row_with_nothing_to_match_on():
    text = HEADER + "\n,,,kill,bi-analytics,2026-09-20,\n"
    decisions, problems = parse_ledger(text)
    assert decisions == []
    assert len(problems) == 1
    assert "jid" in problems[0]


def test_parse_keeps_the_good_rows_when_one_row_is_bad():
    # One malformed row must not cost the human every other decision they made.
    text = VALID + "j3,Bad Row,Data Engineer,perhaps,unsure,2026-09-22,\n"
    decisions, problems = parse_ledger(text)
    assert [d.jid for d in decisions] == ["j1", "j2"]
    assert len(problems) == 1


def test_parse_of_an_empty_file_is_empty_and_not_a_problem():
    assert parse_ledger("") == ([], [])
    assert parse_ledger("\n") == ([], [])


# --- loading and appending ----------------------------------------------------

def test_load_ledger_of_a_missing_file_is_empty():
    # Day one. Nothing has been judged yet, which is not an error.
    assert load_ledger("/nonexistent/decisions.csv") == []


def test_append_writes_a_header_to_a_new_file_then_appends(tmp_path):
    path = tmp_path / "decisions.csv"
    append_decision(path, Decision(
        jid="j1", company="Northwind Analytics", title="Data Engineer",
        verdict="kill", reason="bi-analytics", date="2026-09-20",
        url="https://example.com/j1"))
    append_decision(path, Decision(
        jid="j2", company="Cobalt Grid", title="Data Platform Engineer",
        verdict="draft", reason="strong-fit", date="2026-09-21", url=""))

    lines = path.read_text().splitlines()
    assert lines[0] == HEADER
    assert len(lines) == 3
    decisions, problems = parse_ledger(path.read_text())
    assert problems == []
    assert [d.verdict for d in decisions] == ["kill", "draft"]


def test_append_round_trips_a_comma_bearing_company(tmp_path):
    # Real CSV quoting, not string concatenation — "Northwind Analytics, Inc."
    # would otherwise shift every column after it by one.
    path = tmp_path / "decisions.csv"
    append_decision(path, Decision(
        jid="j1", company="Northwind Analytics, Inc.", title="Data Engineer",
        verdict="kill", reason="bi-analytics", date="2026-09-20", url=""))
    decisions, problems = parse_ledger(path.read_text())
    assert problems == []
    assert decisions[0].company == "Northwind Analytics, Inc."
    assert decisions[0].verdict == "kill"


def test_load_ledger_reads_back_what_append_wrote(tmp_path):
    path = tmp_path / "decisions.csv"
    append_decision(path, Decision(
        jid="j1", company="Northwind Analytics", title="Data Engineer",
        verdict="kill", reason="bi-analytics", date="2026-09-20", url=""))
    assert [d.jid for d in load_ledger(path)] == ["j1"]


# --- matching: tier 1, exact jid ----------------------------------------------

def test_a_posting_matches_its_own_ledger_row_by_jid():
    decisions, _ = parse_ledger(VALID)
    match = prior_verdict(_row(id="j1"), decisions, {}, jid="j1")
    assert match is not None
    assert match.verdict == "kill" and match.reason == "bi-analytics"


def test_an_unjudged_posting_has_no_prior_verdict():
    decisions, _ = parse_ledger(VALID)
    assert prior_verdict(_row(company="Kestrel Dynamics", title="Senior Pipeline Engineer"),
                         decisions, {}, jid="j9") is None


# --- matching: tier 2, the reissued req --------------------------------------

def test_a_reissued_req_matches_on_company_and_title_under_a_new_id():
    # THE motivating case. Same company, same title, a new posting id because
    # the board reissued the req. Tier 1 misses it; tier 2 is why it is caught.
    decisions, _ = parse_ledger(VALID)
    match = prior_verdict(_row(id="brand-new-id"), decisions, {}, jid="brand-new-id")
    assert match is not None
    assert match.verdict == "kill"


def test_company_and_title_matching_ignores_case_spacing_and_a_corporate_suffix():
    decisions, _ = parse_ledger(VALID)
    match = prior_verdict(
        _row(id="new", company="  NORTHWIND   ANALYTICS, Inc. ", title="data engineer"),
        decisions, {}, jid="new")
    assert match is not None
    assert match.verdict == "kill"


def test_a_different_title_at_the_same_company_is_not_a_match():
    # Substring matching on titles would collapse distinct seniorities into one
    # verdict. "Data Engineer" judged does not judge "Data Engineering Manager".
    decisions, _ = parse_ledger(VALID)
    assert prior_verdict(_row(id="new", title="Data Engineering Manager"),
                         decisions, {}, jid="new") is None


# --- matching: tier 3, the body fingerprint ---------------------------------

# A body naming no employer, so a board that reposts it verbatim under its own
# name produces an EQUAL body fingerprint. That is the repost tier 3 can honestly
# carry a verdict across: same posting text, different employer field. A repost
# whose PROSE was rewritten ("Our client, a mid-market analytics firm...") has no
# verdict-inheritance path any more, by design — see the fp_comp note below.
VERBATIM_BODY = ("Own the reporting layer our finance team queries daily. "
                 "We offer medical, dental and a 401k match.")


def _verbatim(jid, company, title):
    return _row(id=jid, company=company, title=title, description=VERBATIM_BODY)


def _state_for(row, jid):
    return {jid: make_entry("2026-09-20", company=row["company"], title=row["title"],
                            fp_comp=fp_comp(row), fp_body=fp_body(row))}


def test_an_aggregator_repost_matches_through_the_body_fingerprint():
    # The board reposts the body verbatim under its own name, so company and title
    # both differ and tier 2 cannot fire. The earlier jid's body fingerprint is in
    # state, and that is what carries the verdict across.
    original = _verbatim("j1", "Northwind Analytics", "Data Engineer")
    state = _state_for(original, "j1")
    decisions, _ = parse_ledger(VALID)

    repost = _verbatim("agg-1", "Talent Reach Staffing", "Data Engineer")
    match = prior_verdict(repost, decisions, state, jid="agg-1")
    assert match is not None
    assert match.verdict == "kill"


def test_a_legacy_state_entry_cannot_produce_a_fingerprint_match():
    # A pre-upgrade state entry has no fingerprints. If None matched None every
    # judged posting would attach its verdict to every unrelated one.
    decisions, _ = parse_ledger(VALID)
    state = {"j1": "2026-09-20"}
    unrelated = _row(id="new", company="Kestrel Dynamics",
                     title="Senior Pipeline Engineer",
                     description="Something else entirely.")
    assert prior_verdict(unrelated, decisions, state, jid="new") is None


def test_the_ledger_never_reports_a_verdict_for_a_posting_it_has_not_seen():
    decisions, _ = parse_ledger(VALID)
    state = {"j1": make_entry("2026-09-20", fp_comp="aaa", fp_body="bbb")}
    other = _row(id="new", company="Kestrel Dynamics", title="Pipeline Engineer",
                 description="A different posting with different benefits.",
                 min_amount=None, max_amount=None)
    assert prior_verdict(other, decisions, state, jid="new") is None


def test_dates_may_be_datetime_objects_when_appending(tmp_path):
    path = tmp_path / "decisions.csv"
    append_decision(path, Decision(
        jid="j1", company="Northwind Analytics", title="Data Engineer",
        verdict="kill", reason="bi-analytics",
        date=datetime.date(2026, 9, 20), url=""))
    assert load_ledger(path)[0].date == "2026-09-20"


# --- the newest decision wins, in every tier (R64-08) ------------------------
#
# A person changes their mind, and the ledger is append-only, so two rows for one
# posting is the normal case rather than an error. Tier 1 happened to return the
# LAST row and tiers 2 and 3 the FIRST, so the same posting reported "draft" when
# it came back under its own id and "kill" when it came back reissued. Whichever
# rule is right, they have to agree.
#
# The rule: the most recent decision wins, by date, with the later ROW winning a
# tie — an append-only file's own order is the only tiebreak it has.

TWICE = HEADER + "\n" + "\n".join([
    "j1,Northwind Analytics,Data Engineer,kill,bi-analytics,2026-09-20,",
    "j1,Northwind Analytics,Data Engineer,draft,reconsidered,2026-09-25,",
]) + "\n"


def test_tier_1_returns_the_newest_decision_for_that_jid():
    decisions, _ = parse_ledger(TWICE)
    assert prior_verdict(_row(id="j1"), decisions, {}, jid="j1").verdict == "draft"


def test_tier_2_returns_the_newest_decision_for_that_company_and_title():
    decisions, _ = parse_ledger(TWICE)
    match = prior_verdict(_row(id="reissued"), decisions, {}, jid="reissued")
    assert match.verdict == "draft"
    assert match.reason == "reconsidered"


def test_tier_3_returns_the_newest_decision_for_that_fingerprint():
    original = _verbatim("j1", "Northwind Analytics", "Data Engineer")
    state = _state_for(original, "j1")
    decisions, _ = parse_ledger(TWICE)
    repost = _verbatim("agg-1", "Talent Reach Staffing", "Data Engineer")
    assert prior_verdict(repost, decisions, state, jid="agg-1").verdict == "draft"


def test_every_tier_agrees_on_which_decision_is_current():
    original = _verbatim("j1", "Northwind Analytics", "Data Engineer")
    state = _state_for(original, "j1")
    decisions, _ = parse_ledger(TWICE)
    by_tier = [
        prior_verdict(_row(id="j1"), decisions, state, jid="j1"),
        prior_verdict(_row(id="new"), decisions, state, jid="new"),
        prior_verdict(_verbatim("agg", "Talent Reach Staffing", "Data Engineer"),
                      decisions, state, jid="agg"),
    ]
    assert {d.verdict for d in by_tier} == {"draft"}


def test_the_newest_decision_wins_even_when_the_rows_are_out_of_order():
    # Someone hand-edits the file, or two sessions append on different days and a
    # sync reorders them. The DATE decides, not the position.
    out_of_order = HEADER + "\n" + "\n".join([
        "j1,Northwind Analytics,Data Engineer,draft,reconsidered,2026-09-25,",
        "j1,Northwind Analytics,Data Engineer,kill,bi-analytics,2026-09-20,",
    ]) + "\n"
    decisions, _ = parse_ledger(out_of_order)
    assert prior_verdict(_row(id="j1"), decisions, {}, jid="j1").verdict == "draft"


def test_two_decisions_on_one_day_are_broken_by_row_order():
    same_day = HEADER + "\n" + "\n".join([
        "j1,Northwind Analytics,Data Engineer,kill,first-read,2026-09-25,",
        "j1,Northwind Analytics,Data Engineer,draft,second-read,2026-09-25,",
    ]) + "\n"
    decisions, _ = parse_ledger(same_day)
    assert prior_verdict(_row(id="j1"), decisions, {}, jid="j1").reason == "second-read"


def test_an_unparseable_date_does_not_win_over_a_real_one():
    # A hand-edited date must not silently become the newest decision.
    odd = HEADER + "\n" + "\n".join([
        "j1,Northwind Analytics,Data Engineer,kill,real-date,2026-09-25,",
        "j1,Northwind Analytics,Data Engineer,draft,no-date,,",
    ]) + "\n"
    decisions, _ = parse_ledger(odd)
    assert prior_verdict(_row(id="j1"), decisions, {}, jid="j1").reason == "real-date"
