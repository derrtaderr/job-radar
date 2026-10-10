"""Which outreach gets replies, and whether a referral moves the interview
rate. Floors and named suppressions exactly as in calibrate.py."""
from engine.loop.calibrate import ContrastResult
from engine.loop.calibrate_paths import (
    control_line, paths_report, referral_result, reply_lines, sends)
from engine.network.touches import Touch


def T(company, slug, state, path="cold_hm", control="no", register="driver",
      hook="build_match", date="2026-10-01"):
    return Touch(date=date, posting_id="", company=company, person_slug=slug,
                 path=path, motive="", hook_level=hook, register=register,
                 control=control, state=state, note="")


def test_a_send_takes_its_dimensions_from_the_ask_and_its_outcome_from_the_latest_row():
    rows = [T("Harborlight", "a", "asked"),
            T("Harborlight", "a", "referred", date="2026-10-03"),
            T("Cobalt Grid", "b", "asked"),
            T("Quarry Systems", "c", "asked"),
            T("Quarry Systems", "c", "no_reply", date="2026-10-20")]
    got = {s.person: s.outcome for s in sends(rows, {})}
    assert got == {"a": "replied", "b": "pending", "c": "no_reply"}


def test_small_groups_are_named_not_dropped():
    rows = [T("Harborlight", "a", "asked"), T("Harborlight", "a", "replied")]
    lines = "\n".join(reply_lines(sends(rows, {}), min_n=5))
    assert "path=cold_hm: too few (N=1, floor 5)" in lines


def test_groups_over_the_floor_print_their_rate():
    rows = []
    for i in range(5):
        rows += [T(f"Co{i}", f"p{i}", "asked")]
        rows += [T(f"Co{i}", f"p{i}", "replied" if i < 2 else "no_reply")]
    lines = "\n".join(reply_lines(sends(rows, {}), min_n=5))
    assert "path=cold_hm: 2 of 5 replied (40%)" in lines


def test_control_contrast_reports_its_ns_when_underpowered():
    rows = [T("Harborlight", "a", "asked", control="yes")]
    assert "too few" in control_line(sends(rows, {}), min_n=5)


def test_referral_result_counts_by_company():
    class App:
        def __init__(self, company, outcome):
            self.company, self.row = company, {"Outcome": outcome}
    # "Offer" classifies as interviewed and "Rejected at screen" as negative
    # (see OUTCOME_MAP in engine/loop/calibrate.py); "Interviewed" would land
    # in `other` and be excluded.
    joined = [App("Harborlight", "Offer"), App("Cobalt Grid", "Rejected at screen")]
    rows = [T("Harborlight, Inc.", "a", "referred", path="warm")]
    result = referral_result(joined, rows, {})
    assert isinstance(result, ContrastResult)
    assert (result.interviewed_hits, result.negative_hits) == (1, 0)


def test_report_never_edits_and_says_so(tmp_path):
    out = paths_report("", tmp_path, [], {}, min_n=5)
    assert "# Path calibration" in out and "never edits config" in out


def test_cli_paths_flag_appends_the_path_report(tmp_path, capsys):
    from tools.calibrate import main
    from tests.fixtures_season import build_season
    season = build_season(tmp_path)
    assert main([str(season.tracker_path), "--archive", str(season.archive_dir),
                 "--config", str(season.config_dir), "--paths"]) == 0
    out = capsys.readouterr().out
    assert "# Calibration report" in out and "# Path calibration" in out
