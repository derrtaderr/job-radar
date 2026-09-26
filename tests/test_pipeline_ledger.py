"""The pipeline reading the ledger and the fingerprints (row 64, misses 1 and 2).

The contract these pin, and it is the whole point of the row: a posting the human
already judged **is never hidden**. It comes back into the queue with its prior
verdict attached, ranked as it would otherwise rank, and the human decides again
with the decision they already made in front of them. Suppressing it would be the
same failure as forgetting it, just quieter.

Every company, title and posting body here is invented.
"""
import datetime
from pathlib import Path

from engine.radar.config import load_config
from engine.radar.ledger import Decision
from engine.radar.pipeline import pipeline
from engine.radar.state import entry_field, fingerprints, seen_date

CFG = load_config(Path(__file__).parent.parent / "config.example")
TODAY = datetime.date(2026, 9, 26)
YESTERDAY = datetime.date(2026, 9, 25)

BENEFITS = ("We offer medical, dental and vision coverage, a 401k match and "
            "unlimited PTO.")


def _row(jid, company="Northwind Analytics", title="Data Engineer",
         description=None, **overrides):
    row = {"id": jid, "company": company, "title": title,
           "description": description or (
               f"{company} is hiring. Own the ingestion layer that feeds our "
               f"reporting marts. {BENEFITS}"),
           "location": "", "is_remote": True,
           "min_amount": 150000, "max_amount": 180000, "interval": "yearly",
           "date_posted": "2026-09-25",
           "job_url": f"https://example.com/jobs/{jid}"}
    row.update(overrides)
    return row


def _killed_by_hand(jid="j1", company="Northwind Analytics",
                    title="Data Engineer", verdict="kill", reason="bi-analytics"):
    return Decision(jid=jid, company=company, title=title, verdict=verdict,
                    reason=reason, date="2026-09-25",
                    url=f"https://example.com/jobs/{jid}")


def _first_run(row):
    """Run one posting through a clean pipeline and hand back the state it
    produced — the shape a second day's run reads."""
    _, _, state = pipeline([row], {}, CFG, set(), YESTERDAY)
    return state


# --- the state a run records --------------------------------------------------

def test_a_run_records_the_company_title_and_both_fingerprints():
    state = _first_run(_row("j1"))
    entry = state["j1"]
    assert seen_date(entry) == str(YESTERDAY)
    assert entry_field(entry, "company") == "Northwind Analytics"
    assert entry_field(entry, "title") == "Data Engineer"
    fp_comp, fp_body = fingerprints(entry)
    assert fp_comp and fp_body


# --- miss 1: the judged req that came back under a new id --------------------

def test_a_judged_req_returning_under_a_new_id_carries_its_verdict():
    # THE motivating case. Same company, same title, same body, a new posting id
    # because the board reissued the req.
    state = _first_run(_row("j1"))
    survivors, killed, _ = pipeline(
        [_row("reissued-id")], state, CFG, set(), TODAY,
        decisions=[_killed_by_hand()])

    assert [r["jid"] for r in survivors] == ["reissued-id"]
    assert survivors[0]["prior"].verdict == "kill"
    assert survivors[0]["prior"].reason == "bi-analytics"
    assert killed == []


def test_a_judged_req_is_never_hidden():
    # Stated as its own test because it is the contract, not a side effect.
    state = _first_run(_row("j1"))
    survivors, killed, _ = pipeline(
        [_row("reissued-id")], state, CFG, set(), TODAY,
        decisions=[_killed_by_hand()])
    assert len(survivors) + len(killed) == 1


def test_a_judged_req_keeps_the_score_it_would_otherwise_have():
    # Attaching a verdict is not re-ranking. The human is the gate; quietly
    # sinking the row would be hiding it by another name.
    state = _first_run(_row("j1"))
    unjudged, _, _ = pipeline([_row("reissued-id")], state, CFG, set(), TODAY)
    judged, _, _ = pipeline([_row("reissued-id")], state, CFG, set(), TODAY,
                            decisions=[_killed_by_hand()])
    assert judged[0]["score"] == unjudged[0]["score"]


def test_a_draft_verdict_attaches_the_same_way():
    state = _first_run(_row("j1"))
    survivors, _, _ = pipeline(
        [_row("reissued-id")], state, CFG, set(), TODAY,
        decisions=[_killed_by_hand(verdict="draft", reason="strong-fit")])
    assert survivors[0]["prior"].verdict == "draft"


def test_an_unjudged_posting_carries_no_prior_verdict():
    survivors, _, _ = pipeline([_row("j1")], {}, CFG, set(), TODAY,
                               decisions=[_killed_by_hand(jid="other",
                                                          company="Kestrel Dynamics",
                                                          title="Pipeline Engineer")])
    assert survivors[0]["prior"] is None


def test_a_killed_row_also_carries_its_prior_verdict():
    # "You already killed this by hand" is worth knowing even when a rule killed
    # it too, because it tells you the rule is doing what you wanted.
    quota = ("Northwind Analytics is hiring. You will carry a quota of 30 "
             "qualified meetings. " + BENEFITS)
    _, killed, _ = pipeline([_row("j1", description=quota)], {}, CFG, set(), TODAY,
                            decisions=[_killed_by_hand(jid="j1")])
    assert killed[0]["prior"].verdict == "kill"


def test_the_pipeline_runs_with_no_ledger_at_all():
    # Day one, and every existing caller that predates the ledger.
    survivors, _, _ = pipeline([_row("j1")], {}, CFG, set(), TODAY)
    assert survivors[0]["prior"] is None


# --- miss 2: reposts are flagged, never suppressed ---------------------------

def test_an_aggregator_repost_is_flagged_against_the_earlier_jid():
    state = _first_run(_row("j1"))
    repost = _row("agg-1", company="Talent Reach Staffing",
                  title="Data Engineer (Client)",
                  description="Our client is hiring. Own the ingestion layer "
                              "that feeds their reporting marts. " + BENEFITS)
    survivors, _, _ = pipeline([repost], state, CFG, set(), TODAY)
    assert survivors[0]["repost_of"] == "j1"


def test_a_same_req_different_territory_pair_is_flagged():
    east = _row("j1", description=(
        "Northwind Analytics is hiring for our Eastern US team. Own the "
        "ingestion layer. " + BENEFITS))
    west = _row("j2", description=(
        "Northwind Analytics is hiring for our Western US team. Own the "
        "ingestion layer. " + BENEFITS))
    survivors, _, _ = pipeline([west], _first_run(east), CFG, set(), TODAY)
    assert survivors[0]["repost_of"] == "j1"


def test_a_repost_within_one_run_is_flagged_too():
    # The per-run (company, title) dedup cannot see this one: the aggregator
    # posts under its own name, so the pair differs.
    original = _row("j1")
    repost = _row("agg-1", company="Talent Reach Staffing",
                  title="Data Engineer (Client)",
                  description="Our client is hiring. Own the ingestion layer "
                              "that feeds their reporting marts. " + BENEFITS)
    survivors, _, _ = pipeline([original, repost], {}, CFG, set(), TODAY)
    assert [r["jid"] for r in survivors] == ["j1", "agg-1"] or \
           [r["jid"] for r in survivors] == ["agg-1", "j1"]
    by_jid = {r["jid"]: r for r in survivors}
    assert by_jid["agg-1"]["repost_of"] == "j1"
    assert by_jid["j1"]["repost_of"] is None


def test_a_repost_is_never_suppressed():
    # The aggregator copy sometimes carries detail the original lacks.
    state = _first_run(_row("j1"))
    repost = _row("agg-1", company="Talent Reach Staffing",
                  title="Data Engineer (Client)")
    survivors, killed, _ = pipeline([repost], state, CFG, set(), TODAY)
    assert len(survivors) + len(killed) == 1


def test_a_repost_of_a_judged_req_carries_the_verdict_too():
    state = _first_run(_row("j1"))
    repost = _row("agg-1", company="Talent Reach Staffing",
                  title="Data Engineer (Client)")
    survivors, _, _ = pipeline([repost], state, CFG, set(), TODAY,
                               decisions=[_killed_by_hand(jid="j1")])
    assert survivors[0]["repost_of"] == "j1"
    assert survivors[0]["prior"].verdict == "kill"


def test_an_unrelated_posting_is_not_flagged_as_a_repost():
    state = _first_run(_row("j1"))
    other = _row("j2", company="Kestrel Dynamics", title="Senior Pipeline Engineer",
                 description="Kestrel Dynamics is hiring. Run the forecasting "
                             "product's streaming stack. We offer equity.",
                 min_amount=None, max_amount=None)
    survivors, _, _ = pipeline([other], state, CFG, set(), TODAY)
    assert survivors[0]["repost_of"] is None


# --- the legacy state file ----------------------------------------------------

def test_a_legacy_state_file_still_suppresses_what_it_has_seen():
    survivors, killed, _ = pipeline([_row("j1")], {"j1": "2026-09-25"}, CFG,
                                    set(), TODAY)
    assert survivors == [] and killed == []


def test_a_legacy_state_entry_produces_no_false_repost_flag():
    # A pre-upgrade entry has no fingerprints. If unknown matched unknown, every
    # posting would read as a repost of the oldest thing in the file.
    survivors, _, _ = pipeline([_row("j2")], {"j1": "2026-09-25"}, CFG, set(), TODAY)
    assert survivors[0]["repost_of"] is None


def test_a_legacy_entry_is_left_exactly_as_it_was():
    # Rewriting it would claim knowledge of a company, title and fingerprints
    # that run never recorded.
    _, _, new_state = pipeline([_row("j2")], {"j1": "2026-09-25"}, CFG, set(), TODAY)
    assert new_state["j1"] == "2026-09-25"


# --- the per-run pair dedup stays per-run ------------------------------------

def test_the_company_and_title_dedup_does_not_suppress_across_runs():
    # Explicitly NOT extended to cross-run suppression. The ledger and the
    # fingerprints are the cross-run mechanism, and they attach rather than hide.
    state = _first_run(_row("j1"))
    survivors, _, _ = pipeline([_row("reissued-id")], state, CFG, set(), TODAY)
    assert [r["jid"] for r in survivors] == ["reissued-id"]


def test_the_company_and_title_dedup_still_works_within_one_run():
    survivors, _, _ = pipeline(
        [_row("a"), _row("b")], {}, CFG, set(), TODAY)
    assert len(survivors) == 1


# --- non-kill notes -----------------------------------------------------------

def test_a_survivor_carries_its_seniority_notes():
    junior = _row("j1", description=(
        "Northwind Analytics is hiring. Own the ingestion layer. We want 1-4 "
        "years of relevant experience. " + BENEFITS))
    survivors, _, _ = pipeline([junior], {}, CFG, set(), TODAY)
    assert "junior-band" in dict(survivors[0]["notes"])


def test_a_survivor_with_nothing_to_note_carries_an_empty_list():
    survivors, _, _ = pipeline([_row("j1")], {}, CFG, set(), TODAY)
    assert survivors[0]["notes"] == []


def test_two_unrelated_postings_sharing_a_comp_band_are_not_reposts():
    # The false positive tools/demo.py surfaced. Nothing but the salary band is
    # shared, and a band is one of the most collision-prone facts a posting has.
    first = _row("j1", company="Northwind Analytics", title="Data Engineer",
                 description="Northwind Analytics is hiring. Own the reporting "
                             "stack. Apply through our portal.")
    second = _row("j2", company="Kestrel Dynamics", title="Senior Pipeline Engineer",
                  description="Kestrel Dynamics is hiring. Run the forecasting "
                              "product. Apply through our portal.")
    survivors, _, _ = pipeline([second], _first_run(first), CFG, set(), TODAY)
    assert survivors[0]["repost_of"] is None
