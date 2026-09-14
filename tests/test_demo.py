"""tools/demo.py — the offline whole-system walk on config.example's
fictional persona. Pins: it exits 0, its queue.md carries the counts and
kill flags tests/fixtures_demo_rows.py was built to produce, its calibration
report carries the same pinned proposals test_loop_e2e.py pins for the same
season fixture, two runs into two different directories produce
byte-identical text artifacts (PDFs are exempt — typst embeds a compile
timestamp, noted rather than hidden), and a machine with no typst on PATH
still exits 0 with a named note instead of a half-written output tree.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.fixtures_demo_rows import (
    EXPECTED_KILL_COUNT,
    EXPECTED_KILL_FLAGS,
    EXPECTED_SURVIVOR_COUNT,
)
from tools import demo

REPO_ROOT = Path(__file__).resolve().parent.parent

pytestmark_no_typst = pytest.mark.skipif(
    shutil.which("typst") is None, reason="typst binary not installed")


def _queue_text(out_dir: Path) -> str:
    day_dir = out_dir / "radar-out" / str(demo.DEMO_TODAY)
    return (day_dir / "queue.md").read_text()


def _calibration_text(out_dir: Path) -> str:
    return (out_dir / "loop-demo" / "calibration-report.md").read_text()


def test_exits_zero(tmp_path):
    assert demo.main(["--out", str(tmp_path / "out")]) == 0


def test_queue_exists_with_expected_survivor_and_kill_counts_and_flags(tmp_path):
    out_dir = tmp_path / "out"
    demo.main(["--out", str(out_dir)])

    text = _queue_text(out_dir)
    assert f"{EXPECTED_SURVIVOR_COUNT} in the queue" in text
    assert f"{EXPECTED_KILL_COUNT} killed by rule" in text
    for flag in EXPECTED_KILL_FLAGS:
        assert f"**{flag}**" in text


def test_calibration_report_exists_with_the_two_pinned_proposals(tmp_path):
    out_dir = tmp_path / "out"
    demo.main(["--out", str(out_dir)])

    report = _calibration_text(out_dir)
    assert (
        "- `weights.yaml`: consider lowering `unlisted_comp_pts` — "
        "5 of 6 interviewed applications had comp listed in the JD, "
        "vs 1 of 7 negative-outcome" in report)
    assert (
        "- `rules.yaml`: consider tightening `rules` — "
        "5 of 7 negative-outcome applications had kill-rule language "
        "in the JD, vs 0 of 6 interviewed" in report)
    assert "## Suppressed proposals" in report
    assert "never edits config" in report


def test_two_runs_into_two_dirs_produce_identical_text_artifacts(tmp_path):
    out_a = tmp_path / "out-a"
    out_b = tmp_path / "out-b"
    demo.main(["--out", str(out_a)])
    demo.main(["--out", str(out_b)])

    assert _queue_text(out_a) == _queue_text(out_b)
    assert _calibration_text(out_a) == _calibration_text(out_b)


def test_rerun_into_the_same_directory_reproduces_the_queue(tmp_path):
    out_dir = tmp_path / "out"
    demo.main(["--out", str(out_dir)])
    first = _queue_text(out_dir)

    demo.main(["--out", str(out_dir)])
    second = _queue_text(out_dir)

    assert first == second


@pytestmark_no_typst
def test_with_typst_on_path_the_drafting_branch_writes_its_artifacts(tmp_path):
    out_dir = tmp_path / "out"
    assert demo.main(["--out", str(out_dir)]) == 0

    draft_dir = out_dir / "drafting"
    assert (draft_dir / "resume.pdf").is_file()
    assert (draft_dir / "cover.pdf").is_file()
    assert (draft_dir / "jd.md").is_file()

    ats_text = (draft_dir / "ats-report.md").read_text()
    assert "python" in ats_text.lower()
    assert "airflow" in ats_text.lower()
    assert "dbt" in ats_text.lower()
    assert "snowflake" in ats_text.lower()


def test_without_typst_prints_a_note_and_still_exits_zero(tmp_path, monkeypatch, capsys):
    # Simulates a machine with no typst installed, matching tests/test_doctor.py's
    # pattern (monkeypatch the module's own `shutil.which`, not a real absence).
    monkeypatch.setattr(demo.shutil, "which", lambda name: None)
    out_dir = tmp_path / "out"

    exit_code = demo.main(["--out", str(out_dir)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "typst not found on PATH" in captured.out
    assert not (out_dir / "drafting").exists()
    # The rest of the demo is unaffected by the missing typst binary.
    assert (out_dir / "radar-out").exists()
    assert (out_dir / "loop-demo" / "calibration-report.md").is_file()


def test_never_sends_line_is_printed(tmp_path, capsys):
    demo.main(["--out", str(tmp_path / "out")])

    captured = capsys.readouterr()
    assert demo.NEVER_SENDS_LINE in captured.out


# --- --out safety: never destroy contents the demo didn't create ----------
#
# Found in review 2026-09-14: _reset_out_dir was an unconditional
# shutil.rmtree on whatever --out resolved to. Pointing it at a directory
# holding an unrelated file silently destroyed the file. A demo built for
# strangers must never be destructive to their filesystem — the probe below
# is the reviewer's exact case.

def test_refuses_to_clear_a_directory_it_did_not_create(tmp_path, capsys):
    out_dir = tmp_path / "out"
    important = out_dir / "important_stuff"
    important.mkdir(parents=True)
    (important / "keep-me.txt").write_text("do not delete me")

    exit_code = demo.main(["--out", str(out_dir)])

    assert exit_code == 2
    # Byte-for-byte survival — not just "the file still exists".
    assert (important / "keep-me.txt").read_text() == "do not delete me"
    assert sorted(p.name for p in out_dir.iterdir()) == ["important_stuff"]

    captured = capsys.readouterr()
    assert (f"--out points at {out_dir.resolve()}, which has contents this "
            "demo did not create — pick an empty or new directory; nothing "
            "was deleted") in captured.out

    # Refused before anything else ran.
    assert not (out_dir / "radar-out").exists()
    assert not (out_dir / "config").exists()


def test_refuses_when_out_points_at_an_existing_file(tmp_path, capsys):
    # --out resolving to a plain file (not a directory) used to fail closed
    # but ugly: _reset_out_dir's `out_dir.iterdir()` raises a raw
    # NotADirectoryError, which surfaces as an unhandled traceback instead of
    # the named, exit-2 refusal every other bad --out gets.
    out_path = tmp_path / "not-a-directory.txt"
    out_path.write_text("i am a file, not a directory")

    exit_code = demo.main(["--out", str(out_path)])

    assert exit_code == 2
    assert out_path.read_text() == "i am a file, not a directory"

    captured = capsys.readouterr()
    assert (f"--out points at {out_path.resolve()}, which is a file, not a "
            "directory — pick an empty or new directory; nothing was "
            "deleted") in captured.out


def test_a_fresh_out_path_that_does_not_exist_yet_succeeds(tmp_path):
    out_dir = tmp_path / "brand-new"
    assert not out_dir.exists()

    assert demo.main(["--out", str(out_dir)]) == 0
    assert (out_dir / demo.DEMO_SENTINEL).is_file()


def test_an_empty_existing_directory_succeeds(tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    assert demo.main(["--out", str(out_dir)]) == 0
    assert (out_dir / demo.DEMO_SENTINEL).is_file()


def test_a_directory_from_a_prior_demo_run_is_reused_not_refused(tmp_path):
    out_dir = tmp_path / "out"
    first = demo.main(["--out", str(out_dir)])
    assert first == 0
    assert (out_dir / demo.DEMO_SENTINEL).is_file()

    # A second run finds the sentinel this demo itself wrote and clears the
    # directory rather than refusing — this is the normal rerun path.
    second = demo.main(["--out", str(out_dir)])
    assert second == 0


def test_cli_subprocess_runs_clean_from_the_repo_root(tmp_path):
    out_dir = tmp_path / "out"
    result = subprocess.run(
        [sys.executable, "tools/demo.py", "--out", str(out_dir)],
        capture_output=True, text=True, cwd=REPO_ROOT)

    assert result.returncode == 0, result.stderr
    assert (out_dir / "radar-out").exists()
    assert (out_dir / "loop-demo" / "calibration-report.md").is_file()
