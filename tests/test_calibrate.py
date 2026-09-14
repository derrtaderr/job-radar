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

    joined, unjoined, ambiguous = join_archives(rows, tmp_path / "archive")

    assert len(joined) == 1
    assert unjoined == []
    assert joined[0].row is rows[0]
    assert joined[0].archive.name == "cobalt-grid-data-engineer"


def test_unjoined_rows_come_back_rather_than_being_dropped(tmp_path):
    # The whole reason both lists are returned: a Closed row with no archive
    # behind it is a data-quality finding, not something to quietly skip.
    (tmp_path / "archive").mkdir()
    rows = outcome_classes(_one("Offer"))["offer"]

    joined, unjoined, ambiguous = join_archives(rows, tmp_path / "archive")

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

    joined, unjoined, ambiguous = join_archives(rows, tmp_path / "archive")

    assert len(joined) == 1 and unjoined == []


def test_a_company_match_alone_is_not_a_join(tmp_path):
    # Same employer, different role, is a different application. Matching on
    # company alone would attribute one posting's JD to another's outcome.
    _archive(tmp_path, "cobalt-grid-analytics-engineer",
             "Cobalt Grid", "Analytics Engineer")
    rows = outcome_classes(_closed(
        "Cobalt Grid | Platform Reliability Engineer | "
        "2026-08-20 | Offer | n/a | n/a"))["offer"]

    joined, unjoined, ambiguous = join_archives(rows, tmp_path / "archive")

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

    joined, unjoined, ambiguous = join_archives(rows, tmp_path / "archive")

    assert len(joined) == 1 and len(unjoined) == 1


def test_a_missing_archive_dir_is_all_unjoined_not_a_crash(tmp_path):
    rows = outcome_classes(_one("Offer"))["offer"]
    joined, unjoined, ambiguous = join_archives(rows, tmp_path / "no-such-archive")
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


# --- calibration_report: the season, and the honesty rules ------------------

def _report(tmp_path, **kwargs):
    from engine.loop.calibrate import calibration_report
    from tests.fixtures_season import build_season
    season = build_season(tmp_path)
    return season, calibration_report(
        season.tracker_text, season.archive_dir, season.cfg, **kwargs)


def _section(report: str, heading: str) -> str:
    """The body under one '## ' heading, up to the next one."""
    assert heading in report, f"no {heading!r} section in report"
    after = report.split(heading, 1)[1]
    return after.split("\n## ", 1)[0]


def test_sections_appear_in_the_contracted_order(tmp_path):
    _, report = _report(tmp_path)
    order = [report.index(h) for h in (
        "## Summary", "## Outcome contrasts", "## Proposals",
        "## Suppressed proposals")]
    assert order == sorted(order)


def test_header_carries_totals_and_the_join_rate(tmp_path):
    season, report = _report(tmp_path)
    summary = _section(report, "## Summary")
    assert season.closed_count == 20 and season.joined_count == 13
    assert "Closed applications: 20" in summary
    assert "Joined to an archive: 13 (65%)" in summary
    assert "Unjoined (no archive match): 7" in summary


def test_header_counts_every_outcome_class(tmp_path):
    _, report = _report(tmp_path)
    summary = _section(report, "## Summary")
    for line in ("- offer: 2", "- rejected-at-screen: 4", "- rejected-later: 4",
                 "- timed-out: 2", "- no-response: 5", "- withdrawn: 2",
                 "- other: 1"):
        assert line in summary, f"missing class count: {line}"


def test_other_bucket_carries_its_outcome_verbatim(tmp_path):
    # The honesty rule: an Outcome the mapping never anticipated must be
    # readable in the report, not folded into a count with no name.
    _, report = _report(tmp_path)
    assert '"Role frozen": 1' in _section(report, "## Summary")


def test_header_documents_the_contrast_grouping(tmp_path):
    # A reader who does not know that "interviewed" means offer plus
    # rejected-later cannot judge a single proposal below it.
    summary = _section(_report(tmp_path)[1], "## Summary")
    assert "offer + rejected-later" in summary
    assert "no-response + rejected-at-screen + timed-out" in summary
    assert "6 joined" in summary and "7 joined" in summary


def test_every_contrast_line_carries_ns_on_both_sides(tmp_path):
    _, report = _report(tmp_path)
    contrasts = _section(report, "## Outcome contrasts")
    assert "- comp listed in the JD: 5 of 6 interviewed (83%) vs 1 of 7 negative-outcome (14%) — 69-point gap" in contrasts
    assert "- remote language in the JD: 4 of 6 interviewed (67%) vs 5 of 7 negative-outcome (71%) — 5-point gap" in contrasts
    assert "- a title-tier hit on the role title: 4 of 6 interviewed (67%) vs 4 of 7 negative-outcome (57%) — 10-point gap" in contrasts
    assert "- kill-rule language in the JD: 0 of 6 interviewed (0%) vs 5 of 7 negative-outcome (71%) — 71-point gap" in contrasts


def test_exactly_two_proposals_clear_the_floor_with_pinned_ns(tmp_path):
    # The spec's done-condition, pinned. Both proposals name the config file
    # and key they suggest changing, and quote their own evidence with Ns.
    _, report = _report(tmp_path)
    proposals = _section(report, "## Proposals")
    assert proposals.count("\n- ") == 2, proposals
    assert (
        "- `weights.yaml`: consider lowering `unlisted_comp_pts` — "
        "6 of 7 negative-outcome applications had unlisted comp, "
        "vs 1 of 6 interviewed (69-point gap, floor N=5)." in proposals)
    assert (
        "- `rules.yaml`: consider tightening `rules` — "
        "6 of 6 interviewed applications had no kill-rule language in the JD, "
        "vs 2 of 7 negative-outcome (71-point gap, floor N=5)." in proposals)


def test_suppressed_section_names_both_underpowered_contrasts(tmp_path):
    _, report = _report(tmp_path)
    suppressed = _section(report, "## Suppressed proposals")
    assert suppressed.count("\n- ") == 2, suppressed
    assert (
        "- remote language in the JD: gap below threshold (5-point gap vs the "
        "20-point threshold; interviewed N=6, negative-outcome N=7, "
        "floor N=5)." in suppressed)
    assert (
        "- a title-tier hit on the role title: gap below threshold (10-point "
        "gap vs the 20-point threshold; interviewed N=6, negative-outcome N=7, "
        "floor N=5)." in suppressed)


def test_every_contrast_lands_in_exactly_one_of_the_two_sections(tmp_path):
    # The invariant that makes the suppressed section trustworthy: four
    # contrasts in, four accounted for. A contrast that appeared in neither
    # would be a silent drop wearing a report's clothes.
    _, report = _report(tmp_path)
    proposed = _section(report, "## Proposals").count("\n- ")
    suppressed = _section(report, "## Suppressed proposals").count("\n- ")
    assert proposed + suppressed == 4


def test_closing_line_states_the_report_never_edits_config(tmp_path):
    _, report = _report(tmp_path)
    assert "never edits config" in report
    assert "by hand" in report


def test_report_is_byte_identical_across_runs(tmp_path):
    # No clock, no randomness, no filesystem listing order. Two runs over the
    # same inputs produce the same bytes or the report cannot be diffed.
    from engine.loop.calibrate import calibration_report
    from tests.fixtures_season import build_season
    season = build_season(tmp_path)
    first = calibration_report(season.tracker_text, season.archive_dir, season.cfg)
    second = calibration_report(season.tracker_text, season.archive_dir, season.cfg)
    assert first == second


def test_raising_min_n_suppresses_both_proposals(tmp_path):
    # min_n is the honesty dial. Turned above the group sizes, nothing may
    # survive into Proposals, and all four contrasts move to suppressed with
    # their real Ns named.
    _, report = _report(tmp_path, min_n=8)
    assert "no proposal cleared the floor" in _section(report, "## Proposals").lower()
    suppressed = _section(report, "## Suppressed proposals")
    assert suppressed.count("\n- ") == 4
    assert "insufficient data" in suppressed
    assert "interviewed N=6" in suppressed and "floor N=8" in suppressed


def test_insufficient_data_names_the_actual_ns_and_the_floor(tmp_path):
    # Pinned on a deliberately thin season rather than the full one: the three
    # JD-text contrasts always share a denominator, so a season cannot show
    # two proposals AND an insufficient-data suppression at once.
    from engine.loop.calibrate import calibration_report
    from tests.fixtures_season import build_config

    tracker = _closed(
        "Cobalt Grid | Data Engineer | 2026-05-01 | Offer | n/a | n/a",
        "Tessellate | Data Engineer | 2026-05-02 | Rejected after onsite | n/a | n/a",
        "Pinecrest Software | Data Engineer | 2026-05-03 | No response | n/a | n/a")
    for slug, company in (("cobalt-grid", "Cobalt Grid"),
                          ("tessellate", "Tessellate"),
                          ("pinecrest", "Pinecrest Software")):
        _archive(tmp_path, slug, company, "Data Engineer")

    from engine.radar.config import load_config
    cfg = load_config(build_config(tmp_path))
    report = calibration_report(tracker, tmp_path / "archive", cfg, min_n=5)

    suppressed = _section(report, "## Suppressed proposals")
    assert suppressed.count("\n- ") == 4
    assert "insufficient data (interviewed N=2, negative-outcome N=1; floor N=5)" in suppressed


def test_unjoined_rows_never_reach_the_contrasts(tmp_path):
    # Seven Closed rows have no archive. The contrast denominators are 6 and
    # 7, not 6 and 11 — a feature cannot be read off a posting nobody kept.
    _, report = _report(tmp_path)
    contrasts = _section(report, "## Outcome contrasts")
    assert "of 11" not in contrasts
    assert "Joined applications only" in contrasts


# --- tools/calibrate.py: the CLI --------------------------------------------
# Fully qualified import, always. `tools.calibrate` and `engine.loop.calibrate`
# share a basename, and a bare `import calibrate` would resolve to whichever
# happened to be on sys.path first.

def test_cli_prints_the_report(tmp_path, capsys):
    from tools.calibrate import main
    from tests.fixtures_season import build_season
    season = build_season(tmp_path)

    code = main([str(season.tracker_path),
                 "--archive", str(season.archive_dir),
                 "--config", str(season.config_dir)])

    out = capsys.readouterr().out
    assert code == 0
    assert "# Calibration report" in out
    assert "`weights.yaml`: consider lowering `unlisted_comp_pts`" in out
    assert "never edits config" in out


def test_cli_writes_the_report_with_out(tmp_path, capsys):
    from tools.calibrate import main
    from tests.fixtures_season import build_season
    season = build_season(tmp_path)
    out_file = tmp_path / "calibration.md"

    code = main([str(season.tracker_path),
                 "--archive", str(season.archive_dir),
                 "--config", str(season.config_dir),
                 "--out", str(out_file)])

    assert code == 0
    assert "# Calibration report" in out_file.read_text()


def test_cli_honors_min_n(tmp_path, capsys):
    from tools.calibrate import main
    from tests.fixtures_season import build_season
    season = build_season(tmp_path)

    main([str(season.tracker_path),
          "--archive", str(season.archive_dir),
          "--config", str(season.config_dir),
          "--min-n", "8"])

    out = capsys.readouterr().out
    assert "No proposal cleared the floor" in out
    assert "floor N=8" in out


def test_cli_defaults_archive_dir_to_the_config(tmp_path, capsys):
    # settings.yaml already names archive_dir. Making the flag mandatory would
    # invite a second, drifting answer to a question the config answers.
    from tools.calibrate import main
    from tests.fixtures_season import build_season
    season = build_season(tmp_path)
    (season.config_dir / "settings.yaml").write_text(
        (season.config_dir / "settings.yaml").read_text()
        + f"\narchive_dir: {season.archive_dir}\n")

    code = main([str(season.tracker_path), "--config", str(season.config_dir)])

    assert code == 0
    assert "Joined to an archive: 13 (65%)" in capsys.readouterr().out


def test_cli_never_writes_into_the_config_dir(tmp_path, capsys):
    # The one thing this tool must never do. Pinned as a test, not just a
    # sentence in the report.
    from tools.calibrate import main
    from tests.fixtures_season import build_season
    season = build_season(tmp_path)
    before = {p.name: p.read_bytes() for p in season.config_dir.iterdir()}

    main([str(season.tracker_path),
          "--archive", str(season.archive_dir),
          "--config", str(season.config_dir)])

    after = {p.name: p.read_bytes() for p in season.config_dir.iterdir()}
    assert before == after


def test_cli_reports_a_missing_tracker_by_name(tmp_path, capsys):
    from tools.calibrate import main
    from tests.fixtures_season import build_season
    season = build_season(tmp_path)

    code = main([str(tmp_path / "no-such-tracker.md"),
                 "--archive", str(season.archive_dir),
                 "--config", str(season.config_dir)])

    assert code == 1
    assert "no-such-tracker.md" in capsys.readouterr().err


# --- C1: similar roles at one company must not cross-join --------------------

def test_two_similar_roles_at_one_company_join_to_their_own_archives(tmp_path):
    # The reviewer's probe. "Data Engineer" is a SUBSTRING of "Analytics Data
    # Engineer", so a substring-first join hands each row whichever archive it
    # meets first — swapping the two JDs, reporting unjoined=[] and a 100%
    # join rate, and corrupting every contrast with no visible symptom.
    # Normalized exact equality has to win before substring is ever tried.
    _archive(tmp_path, "widget-co-data-engineer", "Widget Co", "Data Engineer",
             jd="Base salary range is $165,000 to $195,000 per year.\n")
    _archive(tmp_path, "widget-co-analytics-data-engineer",
             "Widget Co", "Analytics Data Engineer",
             jd="Compensation is competitive.\n")

    rows = outcome_classes(_closed(
        "Widget Co | Data Engineer | 2026-05-01 | Offer | n/a | n/a",
        "Widget Co | Analytics Data Engineer | 2026-05-02 | No response | n/a | n/a"))
    ordered = rows["offer"] + rows["no-response"]

    joined, unjoined, ambiguous = join_archives(ordered, tmp_path / "archive")

    assert unjoined == [] and ambiguous == []
    by_role = {j.row.get("Role"): j.archive.name for j in joined}
    assert by_role == {
        "Data Engineer": "widget-co-data-engineer",
        "Analytics Data Engineer": "widget-co-analytics-data-engineer",
    }


def test_exact_match_wins_even_when_it_sorts_after_a_substring_candidate(tmp_path):
    # Slug order must not decide this. "widget-co-analytics-data-engineer"
    # sorts BEFORE the exact archive, so a first-match-wins substring scan
    # reaches the wrong one first.
    _archive(tmp_path, "widget-co-analytics-data-engineer",
             "Widget Co", "Analytics Data Engineer")
    _archive(tmp_path, "widget-co-data-engineer", "Widget Co", "Data Engineer")

    rows = outcome_classes(_one("Offer"))  # Cobalt Grid, unrelated
    rows = outcome_classes(_closed(
        "Widget Co | Data Engineer | 2026-05-01 | Offer | n/a | n/a"))["offer"]

    joined, unjoined, ambiguous = join_archives(rows, tmp_path / "archive")

    assert len(joined) == 1 and unjoined == [] and ambiguous == []
    assert joined[0].archive.name == "widget-co-data-engineer"


def test_a_genuinely_ambiguous_row_is_unjoined_and_names_its_candidates(tmp_path):
    # No exact match, and TWO archives soft-match. Guessing here is what the
    # critical bug did. The row joins nothing and says which two it could not
    # choose between.
    _archive(tmp_path, "widget-co-data-engineer", "Widget Co", "Data Engineer")
    _archive(tmp_path, "widget-co-analytics-engineer",
             "Widget Co", "Analytics Engineer")

    rows = outcome_classes(_closed(
        "Widget Co | Engineer | 2026-05-01 | Offer | n/a | n/a"))["offer"]

    joined, unjoined, ambiguous = join_archives(rows, tmp_path / "archive")

    assert joined == []
    assert len(unjoined) == 1, "an ambiguous row is still an unjoined row"
    assert len(ambiguous) == 1
    assert ambiguous[0].row is unjoined[0]
    assert sorted(ambiguous[0].candidates) == [
        "widget-co-analytics-engineer", "widget-co-data-engineer"]


def test_substring_fallback_still_joins_when_exactly_one_candidate(tmp_path):
    # The fallback earns its keep: a tracker annotation still joins, because
    # only one archive can possibly be meant.
    _archive(tmp_path, "harborlight-senior-data-engineer",
             "Harborlight", "Senior Data Engineer")
    rows = outcome_classes(_closed(
        "Harborlight Data | Senior Data Engineering | "
        "2026-05-01 | Offer | n/a | n/a"))["offer"]

    joined, unjoined, ambiguous = join_archives(rows, tmp_path / "archive")

    assert len(joined) == 1 and unjoined == [] and ambiguous == []


def test_ambiguous_rows_are_named_in_the_report_header(tmp_path):
    from engine.loop.calibrate import calibration_report
    from tests.fixtures_season import build_config

    _archive(tmp_path, "widget-co-data-engineer", "Widget Co", "Data Engineer")
    _archive(tmp_path, "widget-co-analytics-engineer",
             "Widget Co", "Analytics Engineer")
    tracker = _closed("Widget Co | Engineer | 2026-05-01 | Offer | n/a | n/a")

    from engine.radar.config import load_config
    cfg = load_config(build_config(tmp_path))
    summary = _section(
        calibration_report(tracker, tmp_path / "archive", cfg), "## Summary")

    assert "Ambiguous" in summary
    assert "Widget Co / Engineer" in summary
    assert "widget-co-analytics-engineer" in summary
    assert "widget-co-data-engineer" in summary


# --- M7: rows are joined in TRACKER order, not bucket order -----------------

def test_contested_archive_goes_to_the_earlier_tracker_row(tmp_path):
    # Joining in bucket order would let an `offer` row anywhere in the file
    # claim a contested archive ahead of a `no-response` row above it, which
    # biases the interviewed side of every contrast upward.
    from engine.loop.calibrate import calibration_report, closed_rows
    _archive(tmp_path, "tessellate-data-engineer", "Tessellate", "Data Engineer")
    tracker = _closed(
        "Tessellate | Data Engineer | 2026-05-01 | No response | n/a | n/a",
        "Tessellate | Data Engineer | 2026-08-01 | Offer | n/a | n/a")

    joined, unjoined, _amb = join_archives(
        closed_rows(tracker), tmp_path / "archive")

    assert len(joined) == 1
    assert joined[0].row.get("Outcome") == "No response"
    assert unjoined[0].get("Outcome") == "Offer"


def test_closed_rows_are_returned_in_tracker_order(tmp_path):
    from engine.loop.calibrate import closed_rows
    tracker = _closed(
        "Alpha Data | Data Engineer | 2026-05-01 | No response | n/a | n/a",
        "Beta Systems | Data Engineer | 2026-06-01 | Offer | n/a | n/a",
        "Gamma Works | Data Engineer | 2026-07-01 | Withdrew | n/a | n/a")
    assert [r.get("Company") for r in closed_rows(tracker)] == [
        "Alpha Data", "Beta Systems", "Gamma Works"]


# --- M4: the slug fallback has to be able to match --------------------------

def test_an_archive_with_no_outcome_md_still_joins_by_its_slug(tmp_path):
    # The fallback identity is the slug with hyphens turned back into spaces.
    # Leaving it hyphenated made it unmatchable, which is a fallback that
    # never fires — worse than none, because it looks handled.
    slug_dir = tmp_path / "archive" / "cobalt-grid-data-engineer"
    slug_dir.mkdir(parents=True)
    (slug_dir / "jd.md").write_text("Compensation is competitive.\n")

    rows = outcome_classes(_one("Offer"))["offer"]
    joined, unjoined, ambiguous = join_archives(rows, tmp_path / "archive")

    assert len(joined) == 1 and unjoined == [] and ambiguous == []
    assert joined[0].archive.name == "cobalt-grid-data-engineer"


# --- I2: one application must never carry a proposal ------------------------

def _five_and_five(tmp_path):
    """Five interviewed, five negative, all archived. Comp is the only
    feature that varies: 5 of 5 interviewed vs 4 of 5 negative — a 20-point
    gap that is exactly ONE application of movement at N=5."""
    from tests.fixtures_season import build_applications
    rows = (
        ("Cobalt Grid", "Data Engineer", "Offer", True, True, False, False),
        ("Meridian Analytics", "Data Engineer", "Offer", True, True, False, False),
        ("Tessellate", "Data Engineer", "Rejected after onsite", True, True, False, False),
        ("Harborlight", "Data Engineer", "Rejected after onsite", True, True, False, False),
        ("Voss Continuum", "Data Engineer", "Rejected after onsite", True, True, False, False),
        ("Pinecrest Software", "Data Engineer", "No response", True, True, False, False),
        ("Bellweather Labs", "Data Engineer", "No response", True, True, False, False),
        ("Fernmark Systems", "Data Engineer", "No response", True, True, False, False),
        ("Aldgate Partners", "Data Engineer", "No response", True, True, False, False),
        ("Orrery Compute", "Data Engineer", "No response", True, False, False, False),
    )
    return build_applications(tmp_path, rows)


def test_one_application_of_movement_never_clears_the_floor(tmp_path):
    # At min_n=5 a single application is worth exactly 20 points, so the flat
    # 20-point threshold let ONE application propose a config change. The gap
    # must also clear two applications of movement at the smaller N.
    from engine.loop.calibrate import calibration_report
    season = _five_and_five(tmp_path)

    report = calibration_report(
        season.tracker_text, season.archive_dir, season.cfg, min_n=5)

    contrasts = _section(report, "## Outcome contrasts")
    assert "5 of 5 interviewed (100%) vs 4 of 5 negative-outcome (80%)" in contrasts
    assert "No proposal cleared the floor" in _section(report, "## Proposals")


def test_the_one_application_case_is_named_plainly_in_suppressed(tmp_path):
    from engine.loop.calibrate import calibration_report
    season = _five_and_five(tmp_path)

    suppressed = _section(
        calibration_report(season.tracker_text, season.archive_dir,
                           season.cfg, min_n=5),
        "## Suppressed proposals")

    assert (
        "- comp listed in the JD: gap within one-application noise at these "
        "Ns (20-point gap vs a 40-point floor, which is two applications at "
        "N=5; interviewed N=5, negative-outcome N=5, floor N=5)."
        in suppressed)


def test_noise_floor_is_two_applications_at_the_smaller_n():
    from engine.loop.calibrate import CONTRASTS, ContrastResult
    # The smaller side sets the bar: one application there moves the rate
    # more than one application on the larger side.
    result = ContrastResult(spec=CONTRASTS[0], interviewed_hits=6,
                            interviewed_n=6, negative_hits=0, negative_n=9)
    assert result.noise_floor() == 2 * 100 / 6
    assert result.required_gap() == 2 * 100 / 6  # above the flat 20


def test_flat_threshold_still_governs_at_large_ns():
    from engine.loop.calibrate import CONTRASTS, ContrastResult
    # At N=40 two applications is only 5 points, so the flat 20-point
    # threshold is the binding one. The floor is a max(), never a swap.
    result = ContrastResult(spec=CONTRASTS[0], interviewed_hits=20,
                            interviewed_n=40, negative_hits=10, negative_n=40)
    assert result.noise_floor() == 5.0
    assert result.required_gap() == 20.0


def test_the_seasons_two_proposals_survive_the_noise_floor(tmp_path):
    # At N=6 the noise floor is 33 points. Both pinned proposals clear it
    # (69 and 71), so the fixture needs no adjustment.
    _, report = _report(tmp_path)
    proposals = _section(report, "## Proposals")
    assert proposals.count("\n- ") == 2
    assert "`unlisted_comp_pts`" in proposals and "`rules`" in proposals
