"""Followup staleness scan (engine/loop/followup.py::stale_active).

Fictional companies only (Cobalt Grid, Harborlight, Voss Continuum, Meridian
Analytics, Tessellate) — reuses tests/fixtures_tracker.VALID_TRACKER, the
same fixture test_tracker_schema.py and test_tracker_mutations.py already
share, plus a couple of local variants for the Last-touch edge cases this
suite is specifically about (empty cell, unparseable text, multiple dates in
one annotated cell).
"""
from datetime import date

from engine.loop.followup import StaleRow, stale_active
from tests.fixtures_tracker import VALID_TRACKER

# VALID_TRACKER's Active section, verbatim from fixtures_tracker.py:
#   Cobalt Grid    | Data Platform Engineer | ... | HM round | ... | 2026-09-10               | Send follow-up    | ...
#   Harborlight    | Senior Data Engineer   | ... | Screen   | ... | 2026-09-12 (sent reply)   | Await scheduling  | ...
#   Voss Continuum | Data Engineer          | ... | Applied  | ... | 2026-09-11               | Wait for response | ...

NO_ACTIVE_TABLE = """\
## Closed

| Company | Role | Date closed | Outcome |
|---|---|---|---|
| Meridian Rows | Data Engineer | 2026-08-20 | Rejected |
"""

EMPTY_LAST_TOUCH = """\
## Active

| Company | Role | Stage | Last touch | Next step |
|---|---|---|---|---|
| Cobalt Grid | Data Platform Engineer | HM round | | Send follow-up |
"""

UNPARSEABLE_LAST_TOUCH = """\
## Active

| Company | Role | Stage | Last touch | Next step |
|---|---|---|---|---|
| Cobalt Grid | Data Platform Engineer | HM round | TBD | Send follow-up |
"""

MULTIPLE_DATES_IN_CELL = """\
## Active

| Company | Role | Stage | Last touch | Next step |
|---|---|---|---|---|
| Cobalt Grid | Data Platform Engineer | HM round | 2026-09-01 spoke, 2026-09-05 followed up | Send follow-up |
"""


def test_row_exactly_n_days_quiet_is_stale():
    # 2026-09-10 -> today 2026-09-20 is exactly 10 days quiet.
    stale, unknown = stale_active(VALID_TRACKER, date(2026, 9, 20), 10)
    assert unknown == []
    companies = {r.company for r in stale}
    assert "Cobalt Grid" in companies
    row = next(r for r in stale if r.company == "Cobalt Grid")
    assert row.days_quiet == 10
    assert row.last_touch == date(2026, 9, 10)
    assert row.stage == "HM round"
    assert row.next_step == "Send follow-up"
    assert row.role == "Data Platform Engineer"


def test_row_one_day_short_of_n_is_not_stale():
    # 2026-09-10 -> today 2026-09-19 is 9 days quiet, threshold is 10.
    stale, unknown = stale_active(VALID_TRACKER, date(2026, 9, 19), 10)
    assert "Cobalt Grid" not in {r.company for r in stale}


def test_row_well_past_n_days_is_stale():
    stale, unknown = stale_active(VALID_TRACKER, date(2026, 10, 1), 10)
    companies = {r.company for r in stale}
    # All three Active rows are more than 10 days quiet by 2026-10-01.
    assert companies == {"Cobalt Grid", "Harborlight (via referral)", "Voss Continuum"}


def test_annotated_last_touch_cell_parses_the_date():
    # "2026-09-12 (sent reply)" must still parse as 2026-09-12.
    stale, unknown = stale_active(VALID_TRACKER, date(2026, 9, 22), 10)
    row = next(r for r in stale if r.company == "Harborlight (via referral)")
    assert row.last_touch == date(2026, 9, 12)
    assert unknown == []


def test_cell_with_multiple_dates_takes_the_latest():
    stale, unknown = stale_active(MULTIPLE_DATES_IN_CELL, date(2026, 9, 20), 10)
    assert unknown == []
    row = next(r for r in stale if r.company == "Cobalt Grid")
    # Latest of 2026-09-01 and 2026-09-05 is 2026-09-05 -> 15 days quiet.
    assert row.last_touch == date(2026, 9, 5)
    assert row.days_quiet == 15


def test_empty_last_touch_is_unknown_not_dropped():
    stale, unknown = stale_active(EMPTY_LAST_TOUCH, date(2026, 9, 20), 10)
    assert stale == []
    assert len(unknown) == 1
    row, reason = unknown[0]
    assert row["Company"] == "Cobalt Grid"
    assert "empty" in reason.lower()


def test_unparseable_last_touch_is_unknown_not_dropped():
    stale, unknown = stale_active(UNPARSEABLE_LAST_TOUCH, date(2026, 9, 20), 10)
    assert stale == []
    assert len(unknown) == 1
    row, reason = unknown[0]
    assert row["Company"] == "Cobalt Grid"
    assert "TBD" in reason


def test_no_active_section_returns_empty_both():
    stale, unknown = stale_active(NO_ACTIVE_TABLE, date(2026, 9, 20), 10)
    assert stale == []
    assert unknown == []


def test_empty_text_returns_empty_both():
    stale, unknown = stale_active("", date(2026, 9, 20), 10)
    assert stale == []
    assert unknown == []


def test_stale_row_is_the_documented_dataclass_shape():
    row = StaleRow(company="X", role="Y", last_touch=date(2026, 1, 1),
                   days_quiet=30, stage="Screen", next_step="Follow up")
    assert row.company == "X"
    assert row.days_quiet == 30


# --- CLI: `stale` subcommand -------------------------------------------------

from pathlib import Path  # noqa: E402

from tools.tracker_cli import main as cli_main  # noqa: E402

EXAMPLE_CONFIG = Path(__file__).parent.parent / "config.example"


def _write_tracker(tmp_path, text):
    path = tmp_path / "tracker.md"
    path.write_text(text)
    return path


def test_cli_stale_prints_table_and_exits_0(tmp_path, capsys):
    path = _write_tracker(tmp_path, VALID_TRACKER)
    rc = cli_main(["stale", str(path), "--days", "10", "--today", "2026-09-20"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Cobalt Grid" in out
    assert "10" in out  # days_quiet shown somewhere


def test_cli_stale_no_stale_rows_still_exits_0(tmp_path, capsys):
    path = _write_tracker(tmp_path, VALID_TRACKER)
    rc = cli_main(["stale", str(path), "--days", "10", "--today", "2026-09-11"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Cobalt Grid" not in out


def test_cli_stale_surfaces_unknown_touch(tmp_path, capsys):
    path = _write_tracker(tmp_path, UNPARSEABLE_LAST_TOUCH)
    rc = cli_main(["stale", str(path), "--days", "10", "--today", "2026-09-20"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Cobalt Grid" in out
    assert "TBD" in out


def test_cli_stale_defaults_to_10_days_without_config_flag(tmp_path, capsys):
    path = _write_tracker(tmp_path, VALID_TRACKER)
    # 2026-09-10 -> 2026-09-20 is exactly 10 days: stale under the
    # no-config, no-explicit-days default of 10.
    rc = cli_main(["stale", str(path), "--today", "2026-09-20"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Cobalt Grid" in out


def test_cli_stale_reads_days_from_config(tmp_path, capsys):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    for f in ("queries.yaml", "rules.yaml", "weights.yaml", "exclusions.txt"):
        (config_dir / f).write_text((EXAMPLE_CONFIG / f).read_text())
    settings = _settings_without_followup_key((EXAMPLE_CONFIG / "settings.yaml").read_text())
    settings += "followup_after_days: 5\n"
    (config_dir / "settings.yaml").write_text(settings)

    path = _write_tracker(tmp_path, VALID_TRACKER)
    # 2026-09-10 -> 2026-09-16 is 6 days: NOT stale at the CLI's hardcoded
    # default of 10, but IS stale against the config's followup_after_days: 5.
    rc = cli_main(["stale", str(path), "--config", str(config_dir), "--today", "2026-09-16"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Cobalt Grid" in out


def _settings_without_followup_key(base_text: str) -> str:
    lines = [l for l in base_text.splitlines() if not l.strip().startswith("followup_after_days")]
    return "\n".join(lines) + "\n"
