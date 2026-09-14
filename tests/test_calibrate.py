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
from pathlib import Path

from engine.loop.archive import archive_application
from engine.loop.calibrate import OUTCOME_BUCKETS, join_archives, outcome_classes


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


# --- join_archives: both sides returned, and the misses are countable -------

def _archive(tmp_path: Path, slug: str, company: str, role: str,
             jd: str = "# JD\n") -> Path:
    """One archived application built through the real archive_application,
    not by hand — the join has to work against what that function actually
    writes, not against a shape this test invented."""
    apply_dir = tmp_path / "apply-out" / slug
    apply_dir.mkdir(parents=True)
    (apply_dir / "jd.md").write_text(jd)
    return archive_application(
        apply_dir, tmp_path / "archive",
        {"company": company, "role": role, "applied": "2026-07-01"})


def test_join_matches_on_outcome_frontmatter_company_and_role(tmp_path):
    _archive(tmp_path, "cobalt-grid-data-engineer", "Cobalt Grid", "Data Engineer")
    rows = outcome_classes(_one("Offer"))["offer"]

    joined, unjoined = join_archives(rows, tmp_path / "archive")

    assert len(joined) == 1
    assert unjoined == []
    assert joined[0].row is rows[0]
    assert joined[0].archive.name == "cobalt-grid-data-engineer"


def test_unjoined_rows_come_back_rather_than_being_dropped(tmp_path):
    # The whole reason both lists are returned: a Closed row with no archive
    # behind it is a data-quality finding, not something to quietly skip.
    (tmp_path / "archive").mkdir()
    rows = outcome_classes(_one("Offer"))["offer"]

    joined, unjoined = join_archives(rows, tmp_path / "archive")

    assert joined == []
    assert [r.get("Company") for r in unjoined] == ["Cobalt Grid"]


def test_join_survives_a_tracker_cell_annotation(tmp_path):
    # Tracker cells carry notes a slug never will. _normalize_tracker_cell
    # is imported from the radar rather than reimplemented here.
    _archive(tmp_path, "harborlight-senior-data-engineer",
             "Harborlight", "Senior Data Engineer")
    rows = outcome_classes(_closed(
        "Harborlight (via referral) | Senior Data Engineer | "
        "2026-08-20 | Offer | n/a | n/a"))["offer"]

    joined, unjoined = join_archives(rows, tmp_path / "archive")

    assert len(joined) == 1 and unjoined == []


def test_a_company_match_alone_is_not_a_join(tmp_path):
    # Same employer, different role, is a different application. Matching on
    # company alone would attribute one posting's JD to another's outcome.
    _archive(tmp_path, "cobalt-grid-analytics-engineer",
             "Cobalt Grid", "Analytics Engineer")
    rows = outcome_classes(_closed(
        "Cobalt Grid | Platform Reliability Engineer | "
        "2026-08-20 | Offer | n/a | n/a"))["offer"]

    joined, unjoined = join_archives(rows, tmp_path / "archive")

    assert joined == [] and len(unjoined) == 1


def test_each_archive_is_consumed_once(tmp_path):
    # A repeat application to the same company and role is legitimate in the
    # Closed section (tracker_schema allows it by design). Two rows must not
    # both claim the one archive, or every feature it carries gets
    # double-counted in the contrasts.
    _archive(tmp_path, "tessellate-data-engineer", "Tessellate", "Data Engineer")
    rows = outcome_classes(_closed(
        "Tessellate | Data Engineer | 2026-04-02 | Offer | n/a | n/a",
        "Tessellate | Data Engineer | 2026-08-20 | Offer | n/a | n/a"))["offer"]

    joined, unjoined = join_archives(rows, tmp_path / "archive")

    assert len(joined) == 1 and len(unjoined) == 1


def test_a_missing_archive_dir_is_all_unjoined_not_a_crash(tmp_path):
    rows = outcome_classes(_one("Offer"))["offer"]
    joined, unjoined = join_archives(rows, tmp_path / "no-such-archive")
    assert joined == [] and len(unjoined) == 1


def test_join_is_deterministic_across_archive_listing_order(tmp_path):
    for slug, company in (("zenith-data-engineer", "Zenith Works"),
                          ("acorn-data-engineer", "Acorn Metrics")):
        _archive(tmp_path, slug, company, "Data Engineer")
    rows = outcome_classes(_closed(
        "Acorn Metrics | Data Engineer | 2026-08-20 | Offer | n/a | n/a"))["offer"]

    first = join_archives(rows, tmp_path / "archive")[0][0].archive.name
    second = join_archives(rows, tmp_path / "archive")[0][0].archive.name
    assert first == second == "acorn-data-engineer"
