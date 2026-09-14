"""Pin engine/loop/calibrate.py's contract — the module that turns resolved
application outcomes into rule-tuning PROPOSALS a human applies by hand.

The honesty rules are the point of this file, more than the arithmetic:

- every Closed row lands in a named bucket, and an Outcome nobody anticipated
  lands in `other` VERBATIM rather than being dropped;
- a Closed row with no archive behind it is COUNTED (the join rate is itself a
  data-quality signal), never quietly excluded;
- a contrast that failed the floor is NAMED in a suppressed section with its
  actual Ns, never omitted so the report looks more confident than the data;
- nothing here ever writes config.

Every company, role, and JD in these fixtures is fictional.

NOTE: `engine.loop.calibrate` and `tools.calibrate` share a basename. Imports
in this file stay fully qualified for that reason (house precedent: compile.py).
"""
from engine.loop.calibrate import OUTCOME_BUCKETS, outcome_classes


def _closed(*rows: str) -> str:
    """A minimal tracker whose Closed section carries `rows` (already
    pipe-delimited bodies, minus the leading/trailing pipes)."""
    header = (
        "## Closed\n\n"
        "| Company | Role | Date closed | Outcome | Reason | Carry-forward lesson |\n"
        "|---|---|---|---|---|---|\n")
    return header + "".join(f"| {r} |\n" for r in rows)


def _one(outcome: str) -> str:
    return _closed(f"Cobalt Grid | Data Engineer | 2026-08-20 | {outcome} | n/a | n/a")


def _bucket_of(outcome: str) -> str:
    classes = outcome_classes(_one(outcome))
    hits = [name for name, rows in classes.items() if rows]
    assert len(hits) == 1, f"{outcome!r} landed in {hits}, expected exactly one bucket"
    return hits[0]


# --- outcome_classes: the mapping table -------------------------------------

def test_every_bucket_is_present_even_when_empty():
    # A report that silently omits an empty class reads as though the class
    # never happened. Every bucket is always a key, in a fixed order.
    classes = outcome_classes(_one("Offer"))
    assert list(classes) == list(OUTCOME_BUCKETS)


def test_offer_variants():
    assert _bucket_of("Offer") == "offer"
    assert _bucket_of("Offer declined") == "offer"


def test_screen_rejection_beats_the_generic_rejected_match():
    # "Rejected at screen" carries BOTH substrings. Screen wins, or every
    # screen rejection would silently inflate the interviewed side.
    assert _bucket_of("Rejected at screen") == "rejected-at-screen"
    assert _bucket_of("Rejected after recruiter screen") == "rejected-at-screen"
    assert _bucket_of("Screened out") == "rejected-at-screen"


def test_later_stage_rejections():
    assert _bucket_of("Rejected after onsite") == "rejected-later"
    assert _bucket_of("Rejected at final round") == "rejected-later"


def test_timed_out_variants():
    assert _bucket_of("Timed out") == "timed-out"
    assert _bucket_of("Timeout, role refilled") == "timed-out"


def test_no_response_variants():
    assert _bucket_of("No response") == "no-response"
    assert _bucket_of("Ghosted") == "no-response"
    assert _bucket_of("Silence") == "no-response"


def test_withdrawn_variants():
    assert _bucket_of("Withdrew") == "withdrawn"
    assert _bucket_of("Withdrawn by me") == "withdrawn"


def test_matching_is_case_insensitive():
    assert _bucket_of("OFFER") == "offer"
    assert _bucket_of("no RESPONSE") == "no-response"


def test_unmatched_outcome_lands_in_other_verbatim():
    # The whole point of `other`: an Outcome the mapping never anticipated is
    # VISIBLE, carrying the text the human actually typed.
    classes = outcome_classes(_one("Role frozen"))
    assert [r.get("Outcome") for r in classes["other"]] == ["Role frozen"]


def test_blank_outcome_lands_in_other():
    classes = outcome_classes(_closed(
        "Cobalt Grid | Data Engineer | 2026-08-20 |  | n/a | n/a"))
    assert len(classes["other"]) == 1


def test_rows_keep_their_tracker_identity():
    classes = outcome_classes(_one("Offer"))
    row = classes["offer"][0]
    assert row.get("Company") == "Cobalt Grid"
    assert row.get("Role") == "Data Engineer"


def test_only_the_closed_section_is_read():
    text = (
        "## Active\n\n"
        "| Company | Role | Last touch |\n"
        "|---|---|---|\n"
        "| Tessellate | Data Engineer | 2026-09-10 |\n\n"
        + _one("Offer"))
    classes = outcome_classes(text)
    assert sum(len(rows) for rows in classes.values()) == 1


def test_a_tracker_with_no_closed_section_yields_empty_buckets():
    text = ("## Active\n\n| Company | Role | Last touch |\n|---|---|---|\n"
            "| Tessellate | Data Engineer | 2026-09-10 |\n")
    classes = outcome_classes(text)
    assert list(classes) == list(OUTCOME_BUCKETS)
    assert sum(len(rows) for rows in classes.values()) == 0
