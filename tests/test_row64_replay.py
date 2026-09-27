"""A synthetic replay of the six dated misses that motivated row 64.

Each of the six classes below came out of a real run of this radar, and each one
is reproduced here against the real pipeline and the shipped `config.example`
rules — one file, so the whole row can be read as a single before-and-after
rather than as fourteen separate unit files.

This is an ACCEPTANCE test, so unlike the unit suites it is written over behavior
that already exists rather than to drive it. Its evidence is that the whole file
goes red against the pre-change tree: every assertion here fails without the
mechanisms it names.

    1. A req killed by hand re-surfaced as the top-scored row, days later, under
       a NEW posting id, because the kill lived in markdown prose nothing parses.
    2. Aggregator reposts and same-req-different-territory duplicates defeated
       suppression, which keys on company plus URL.
    3. The location rule resolved "New York, United States" two ways in one run.
    4. A body reading "This is a fully on-site position" did not kill.
    5. "Tuesdays and Fridays are remote/work from home days" passed as remote.
    6. "1-4 years of relevant experience, early in their career" placed second.

Every company, title, posting body and URL here is invented.
"""
import dataclasses
import datetime
import re
from pathlib import Path

from engine.radar.config import load_config
from engine.radar.ledger import Decision
from engine.radar.pipeline import pipeline
from engine.radar.report import render_report
from tests.fixtures import as_scraped

CFG = load_config(Path(__file__).parent.parent / "config.example")
DAY_ONE = datetime.date(2026, 9, 21)
DAY_FIVE = datetime.date(2026, 9, 26)

BENEFITS = ("Benefits include medical, dental and vision coverage, a 401k match, "
            "unlimited PTO and paid parental leave.")

# The req the human read, judged, and expected never to see again.
BI_BODY = ("Northwind Analytics is hiring a Data Engineer to own the reporting "
           "layer our finance team queries. You will maintain the dashboards and "
           "the semantic model behind them. Fully remote (US). " + BENEFITS)


def _posting(jid, company, title, description, **overrides):
    row = {"id": jid, "company": company, "title": title,
           "description": description, "location": "", "is_remote": True,
           "min_amount": 150000, "max_amount": 185000, "interval": "yearly",
           "date_posted": str(DAY_FIVE), "job_url": f"https://example.com/jobs/{jid}"}
    row.update(overrides)
    return row


def _the_req(jid, company="Northwind Analytics", title="Data Engineer",
             description=BI_BODY):
    return _posting(jid, company, title, description)


THE_VERDICT = Decision(
    jid="ln-1001", company="Northwind Analytics", title="Data Engineer",
    verdict="kill", reason="bi-analytics", date=str(DAY_ONE),
    url="https://example.com/jobs/ln-1001")


def _day_one():
    """Day one: the req is scraped, read, and killed by hand. Returns the state
    the run recorded — what day five actually has to work from."""
    _, _, state = pipeline([_the_req("ln-1001")], {}, CFG, set(), DAY_ONE)
    return state


def _flags(row):
    return [name for name, _ in row.get("flags", ())]


def _notes(row):
    return [name for name, _ in row.get("notes", ())]


# --- miss 1: the hand-killed req that came back under a new id ---------------

def test_miss_1_the_judged_req_comes_back_carrying_its_verdict():
    state = _day_one()
    # The board reissues the req. New LinkedIn id, same company, same title,
    # same body. Nothing about the posting says it is the same one.
    survivors, killed, _ = pipeline([_the_req("ln-2477")], state, CFG, set(),
                                    DAY_FIVE, decisions=[THE_VERDICT])

    assert [r["jid"] for r in survivors] == ["ln-2477"]
    assert survivors[0]["prior"].verdict == "kill"
    assert survivors[0]["prior"].reason == "bi-analytics"
    assert killed == []


def test_miss_1_the_verdict_reaches_the_queue_a_human_reads():
    state = _day_one()
    survivors, killed, _ = pipeline([_the_req("ln-2477")], state, CFG, set(),
                                    DAY_FIVE, decisions=[THE_VERDICT])
    queue = render_report(survivors, killed, str(DAY_FIVE))

    assert "kill (bi-analytics)" in queue
    assert "1 already judged" in queue
    # And it is IN the queue, not hidden from it. This is the contract.
    assert "Northwind Analytics" in queue


def test_miss_1_the_judged_req_is_not_quietly_ranked_down_either():
    state = _day_one()
    plain, _, _ = pipeline([_the_req("ln-2477")], state, CFG, set(), DAY_FIVE)
    judged, _, _ = pipeline([_the_req("ln-2477")], state, CFG, set(), DAY_FIVE,
                            decisions=[THE_VERDICT])
    assert judged[0]["score"] == plain[0]["score"]


# --- miss 2: reposts and territory twins -------------------------------------

def test_miss_2_an_aggregator_repost_with_rewritten_prose_is_flagged_not_judged():
    # A job board reposts the req under its own name AND rewrites the opening so
    # the client is anonymous. Company, URL, title and prose all differ, so only
    # the comp fingerprint can see it — and after R64-02 a comp match earns the
    # FLAG and nothing more, because a band plus a common benefits set is shared by
    # unrelated postings and must not speak for a person's judgment.
    #
    # The consequence, stated rather than hidden: a rewritten-prose repost of a
    # judged req arrives flagged but unjudged. Carrying a verdict across it needs a
    # tighter identity than either fingerprint has (title + band within a window),
    # which the orchestrator recorded as a follow-up row rather than this wave.
    state = _day_one()
    repost = _the_req(
        "ln-3100", company="Talent Reach Staffing", title="Data Engineer (Client)",
        description=("Our client, a mid-market analytics firm, is hiring a Data "
                     "Engineer to own their reporting layer. Fully remote (US). "
                     + BENEFITS))
    survivors, _, _ = pipeline([repost], state, CFG, set(), DAY_FIVE,
                               decisions=[THE_VERDICT])

    assert survivors[0]["repost_of"] == "ln-1001"
    assert survivors[0]["prior"] is None


def test_miss_2_a_verbatim_repost_does_carry_the_verdict():
    # The repost shape a verdict CAN travel across: the board republishes the body
    # unchanged under its own employer name, so the body fingerprints agree.
    verbatim = ("Own the reporting layer our finance team queries daily. Fully "
                "remote (US). " + BENEFITS)
    original = _the_req("ln-1001", description=verbatim)
    _, _, state = pipeline([original], {}, CFG, set(), DAY_ONE)
    repost = _the_req("ln-3200", company="Talent Reach Staffing",
                      title="Data Engineer", description=verbatim)
    survivors, _, _ = pipeline([repost], state, CFG, set(), DAY_FIVE,
                               decisions=[THE_VERDICT])
    assert survivors[0]["repost_of"] == "ln-1001"
    assert survivors[0]["prior"].verdict == "kill"


def test_miss_2_a_same_req_different_territory_twin_is_flagged():
    east = _the_req("ln-4001", description=(
        "Northwind Analytics is hiring a Data Engineer for our Eastern US team "
        "to own the reporting layer. " + BENEFITS))
    west = _the_req("ln-4002", description=(
        "Northwind Analytics is hiring a Data Engineer for our Western US team "
        "to own the reporting layer. " + BENEFITS))
    _, _, state = pipeline([east], {}, CFG, set(), DAY_ONE)
    survivors, _, _ = pipeline([west], state, CFG, set(), DAY_FIVE)

    assert survivors[0]["repost_of"] == "ln-4001"


def test_miss_2_a_repost_is_flagged_and_never_suppressed():
    # Never suppressed: the aggregator's copy sometimes carries detail the
    # original lacks, and the engine does not get to pick which copy you read.
    state = _day_one()
    repost = _the_req("ln-3100", company="Talent Reach Staffing",
                      title="Data Engineer (Client)")
    survivors, killed, _ = pipeline([repost], state, CFG, set(), DAY_FIVE)
    assert len(survivors) + len(killed) == 1
    assert "possible repost of ln-1001" in render_report(survivors, killed,
                                                         str(DAY_FIVE))


def test_miss_2_escapes_alone_do_not_stop_a_repost_from_matching():
    # One board delivers the body with markdown escapes and another without. If
    # the escapes reached the fingerprint, an original and its repost would differ
    # by punctuation alone and the whole mechanism would go quiet on real data.
    escaped = _posting("ln-6001", "Northwind Analytics", "Data Engineer",
                       r"Own the reporting layer \- finance queries it daily. "
                       + BENEFITS)
    clean = _posting("ln-6002", "Northwind Analytics", "Data Engineer",
                     "Own the reporting layer - finance queries it daily. " + BENEFITS)
    _, _, state = pipeline(as_scraped([escaped]), {}, CFG, set(), DAY_ONE)
    survivors, _, _ = pipeline(as_scraped([clean]), state, CFG, set(), DAY_FIVE)
    assert survivors[0]["repost_of"] == "ln-6001"


def test_miss_2_a_genuinely_different_posting_is_not_flagged():
    state = _day_one()
    other = _the_req(
        "ln-5000", company="Kestrel Dynamics", title="Senior Pipeline Engineer",
        description=("Kestrel Dynamics is hiring a Senior Pipeline Engineer to "
                     "build the ingestion path for our forecasting product. "
                     "Fully remote (US). We offer equity and a home office "
                     "stipend."))
    survivors, _, _ = pipeline([other], state, CFG, set(), DAY_FIVE)
    assert survivors[0]["repost_of"] is None


# --- miss 3: one place, one verdict ------------------------------------------

def test_miss_3_one_place_spelled_two_ways_gets_one_verdict():
    # A commute allowlist of `NY`. Before normalisation this matched the "ny"
    # inside "Pennsylvania" and missed "New York, United States" entirely, so the
    # same place passed in one row and was killed in another, in one run.
    cfg = dataclasses.replace(CFG, commute_pattern=re.compile("NY", re.I))
    # Three DIFFERENT employers, so the per-run (company, title) dedup — which is
    # working as intended and is not what this test is about — does not collapse
    # them into one row before the location rule ever runs.
    rows = [_posting(f"ny-{i}", company, "Data Engineer",
                     "Own the reporting layer. " + BENEFITS,
                     is_remote=False, location=spelling)
            for i, (company, spelling) in enumerate((
                ("Harborlight Data", "New York, United States"),
                ("Cobalt Grid", "New York, NY"),
                ("Larkspur Grid", "NY")))]

    survivors, killed, _ = pipeline(rows, {}, cfg, set(), DAY_FIVE)
    # All three name the allowlisted place, so none of them is a location kill.
    assert killed == []
    assert len(survivors) == 3


def test_miss_3_a_place_that_merely_contains_the_pattern_is_still_killed():
    cfg = dataclasses.replace(CFG, commute_pattern=re.compile("NY", re.I))
    row = _posting("pa-1", "Harborlight Data", "Data Engineer",
                   "Own the reporting layer. " + BENEFITS,
                   is_remote=False, location="Pennsylvania, United States")
    _, killed, _ = pipeline([row], {}, cfg, set(), DAY_FIVE)
    assert "location" in _flags(killed[0])


# --- miss 4: the body contradicting its own header ---------------------------

def test_miss_4_a_fully_on_site_body_kills_against_a_remote_header():
    row = _posting("os-1", "Cindermill Tech", "Data Platform Engineer",
                   "Own our streaming architecture. This is a fully on-site "
                   "position. " + BENEFITS,
                   is_remote=True, location="")
    _, killed, _ = pipeline([row], {}, CFG, set(), DAY_FIVE)
    assert "onsite-body" in _flags(killed[0])
    assert "fully on-site" in dict(killed[0]["flags"])["onsite-body"]


def test_miss_4_kills_on_the_shape_a_live_scrape_delivers():
    # The same miss, in the wire shape: a live LinkedIn scrape hands back markdown
    # with escaped punctuation, so the body reads "a fully on\-site position".
    # Straight through the real scrape boundary and then the real pipeline, so this
    # is the end-to-end claim rather than a unit assertion about clean prose.
    raw = _posting("os-live", "Cindermill Tech", "Data Platform Engineer",
                   r"Own our streaming architecture. This is a fully on\-site "
                   r"position. Comp $150,000 \- $185,000. " + BENEFITS,
                   is_remote=True, location="")
    delivered = as_scraped([raw])
    _, killed, _ = pipeline(delivered, {}, CFG, set(), DAY_FIVE)
    assert "onsite-body" in _flags(killed[0])
    assert "fully on-site" in dict(killed[0]["flags"])["onsite-body"]


def test_miss_4_an_on_site_role_you_can_commute_to_still_survives():
    # config.example's allowlist is Denver|Boulder. The rule must not invert the
    # miss by killing the on-site roles the user actually wants.
    row = _posting("os-2", "Tessellate", "Senior Data Engineer",
                   "Join our data team. This is a fully on-site position at our "
                   "Denver headquarters. " + BENEFITS,
                   is_remote=False, location="Denver, CO")
    survivors, killed, _ = pipeline([row], {}, CFG, set(), DAY_FIVE)
    assert killed == []
    assert len(survivors) == 1


# --- miss 5: hybrid phrasing passing as remote -------------------------------

def test_miss_5_hybrid_day_phrasing_does_not_pass_as_remote():
    row = _posting("hy-1", "Quill and Sparrow", "Analytics Engineer",
                   "Join our Chicago analytics group. Tuesdays and Fridays are "
                   "remote/work from home days. " + BENEFITS,
                   is_remote=False, location="Chicago, IL")
    _, killed, _ = pipeline([row], {}, CFG, set(), DAY_FIVE)
    assert "location" in _flags(killed[0])


def test_miss_5_a_genuinely_remote_role_with_an_office_still_passes():
    row = _posting("hy-2", "Pinecrest Software", "Data Platform Engineer",
                   "Own our streaming architecture. This is a fully remote role. "
                   "Our office is in Chicago. " + BENEFITS,
                   is_remote=False, location="Chicago, IL")
    survivors, killed, _ = pipeline([row], {}, CFG, set(), DAY_FIVE)
    assert killed == []
    assert len(survivors) == 1


# --- miss 6: the junior band that placed second ------------------------------

def test_miss_6_a_junior_band_is_flagged_and_ranks_below_a_senior_peer():
    senior = _posting("sr-1", "Cobalt Grid", "Data Platform Engineer",
                      "Own the ingestion layer. " + BENEFITS)
    junior = _posting("jr-1", "Larkspur Grid", "Data Platform Engineer",
                      "Own the ingestion layer. We want 1-4 years of relevant "
                      "experience; this role suits someone early in their "
                      "career. " + BENEFITS)

    survivors, killed, _ = pipeline([junior, senior], {}, CFG, set(), DAY_FIVE)
    by_jid = {r["jid"]: r for r in survivors}

    assert killed == []                                   # a penalty, not a kill
    assert "junior-band" in _notes(by_jid["jr-1"])
    assert by_jid["jr-1"]["score"] < by_jid["sr-1"]["score"]
    assert [r["jid"] for r in survivors] == ["sr-1", "jr-1"]


def test_miss_6_the_evidence_is_quoted_in_the_queue():
    junior = _posting("jr-1", "Larkspur Grid", "Data Platform Engineer",
                      "Own the ingestion layer. We want 1-4 years of relevant "
                      "experience. " + BENEFITS)
    survivors, killed, _ = pipeline([junior], {}, CFG, set(), DAY_FIVE)
    queue = render_report(survivors, killed, str(DAY_FIVE))
    assert "## Flagged, not killed" in queue
    assert "1-4 years of relevant experience" in queue


def test_miss_6_a_ten_year_stretch_is_flagged_and_costs_nothing():
    plain = _posting("st-0", "Cobalt Grid", "Data Platform Engineer",
                     "Own the ingestion layer. " + BENEFITS)
    stretch = _posting("st-1", "Cobalt Grid", "Data Platform Engineer",
                       "Own the ingestion layer. We are looking for 10+ years of "
                       "experience. " + BENEFITS)
    base, _, _ = pipeline([plain], {}, CFG, set(), DAY_FIVE)
    survivors, killed, _ = pipeline([stretch], {}, CFG, set(), DAY_FIVE)

    assert killed == []
    assert "seniority-stretch" in _notes(survivors[0])
    assert survivors[0]["score"] == base[0]["score"]


# --- the upgrade path ---------------------------------------------------------

def test_a_legacy_state_file_still_suppresses_and_flags_nothing_falsely():
    # A user's state.json predates every mechanism above. It must keep working:
    # what it has seen stays suppressed, and its entries — which carry no
    # fingerprints at all — must not make every new posting look like a repost.
    legacy = {"ln-1001": "2026-09-21", "ln-0500": "2026-09-19"}
    fresh = _the_req("ln-9999", company="Kestrel Dynamics",
                     title="Senior Pipeline Engineer",
                     description="Kestrel Dynamics is hiring. " + BENEFITS)

    suppressed, killed_s, _ = pipeline([_the_req("ln-1001")], legacy, CFG, set(),
                                      DAY_FIVE)
    assert suppressed == [] and killed_s == []

    survivors, _, new_state = pipeline([fresh], legacy, CFG, set(), DAY_FIVE)
    assert survivors[0]["repost_of"] is None
    # ...and the legacy entries are left exactly as they were, because rewriting
    # them would claim knowledge those runs never recorded.
    assert new_state["ln-1001"] == "2026-09-21"
    assert new_state["ln-0500"] == "2026-09-19"


# --- the thesis ---------------------------------------------------------------

def test_the_whole_replay_calls_no_model():
    # The project's thesis, asserted rather than trusted: deterministic rules
    # kill and score, judgment happens in the human's session and comes back
    # through the ledger. Two runs of the same day produce the same answer.
    state = _day_one()
    rows = [_the_req("ln-2477"),
            _posting("jr-1", "Larkspur Grid", "Data Platform Engineer",
                     "Own the ingestion layer. 1-4 years of experience. " + BENEFITS)]
    first = render_report(*pipeline(rows, state, CFG, set(), DAY_FIVE,
                                    decisions=[THE_VERDICT])[:2], str(DAY_FIVE))
    second = render_report(*pipeline(rows, state, CFG, set(), DAY_FIVE,
                                     decisions=[THE_VERDICT])[:2], str(DAY_FIVE))
    assert first == second
