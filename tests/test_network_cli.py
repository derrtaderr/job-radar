"""network_cli: the only writer of config/network/. Fictional data only."""
import datetime
import json
import shutil
from pathlib import Path

from engine.network.touches import load_touches
from engine.radar.config import load_config
from tools.network_cli import main

EXAMPLE = Path(__file__).parent.parent / "config.example"
MON = datetime.date(2026, 10, 12)


def _cfg(tmp_path):
    cfg_dir = tmp_path / "config"
    shutil.copytree(EXAMPLE, cfg_dir)
    shutil.rmtree(cfg_dir / "network", ignore_errors=True)
    net = cfg_dir / "network"
    net.mkdir()
    (net / "connections.csv").write_text(
        "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
        "Ana,Rivera,https://www.linkedin.com/in/example,,Harborlight,Engineer,15 Jan 2019\n")
    return cfg_dir


def run(cfg_dir, *argv, today=MON):
    return main(["--config", str(cfg_dir), *argv], today=today)


def test_config_carries_network_dir(tmp_path):
    cfg_dir = _cfg(tmp_path)
    assert load_config(cfg_dir).network_dir == cfg_dir / "network"


def test_add_writes_a_people_file(tmp_path, capsys):
    cfg_dir = _cfg(tmp_path)
    assert run(cfg_dir, "add", "--company", "Harborlight", "--result", "found",
               "--person", "Dee Marsh|VP Growth|https://example.com/dm|hiring_manager") == 0
    assert (cfg_dir / "network" / "people" / "harborlight.yaml").exists()
    assert run(cfg_dir, "add", "--company", "Quarry Systems", "--result", "found",
               "--person", "Bad|Row") == 2
    assert "Name|Title|URL|role" in capsys.readouterr().out


def test_gate_exit_codes_follow_the_touches(tmp_path):
    cfg_dir = _cfg(tmp_path)
    assert run(cfg_dir, "gate", "Harborlight") == 3
    assert run(cfg_dir, "touch", "--company", "Harborlight", "--person", "ana-rivera",
               "--path", "warm", "--motive", "referral_ask",
               "--hook", "shared_history", "--state", "asked") == 0
    assert run(cfg_dir, "gate", "Harborlight") == 4
    assert run(cfg_dir, "gate", "Harborlight", today=datetime.date(2026, 10, 15)) == 0
    assert run(cfg_dir, "gate", "Cobalt Grid") == 0


def test_dry_run_writes_nothing(tmp_path, capsys):
    cfg_dir = _cfg(tmp_path)
    assert run(cfg_dir, "touch", "--company", "Harborlight", "--state", "override",
               "--dry-run") == 0
    assert "override" in capsys.readouterr().out
    assert not (cfg_dir / "network" / "touches.csv").exists()


def test_touch_refuses_an_unknown_posting_id(tmp_path, capsys):
    cfg_dir = _cfg(tmp_path)
    assert run(cfg_dir, "touch", "--company", "Harborlight", "--posting", "zzz",
               "--state", "applied") == 2
    assert "no record of posting" in capsys.readouterr().out
    (cfg_dir / "state.json").write_text(json.dumps({"j9": {"seen": "2026-10-10"}}))
    assert run(cfg_dir, "touch", "--company", "Harborlight", "--posting", "j9",
               "--state", "applied") == 0


def test_reply_needs_a_recorded_ask_and_left_company_marks_the_file(tmp_path):
    cfg_dir = _cfg(tmp_path)
    assert run(cfg_dir, "reply", "--company", "Harborlight", "--person", "dee-marsh",
               "--state", "replied") == 2
    run(cfg_dir, "add", "--company", "Harborlight", "--result", "found",
        "--person", "Dee Marsh|VP Growth|https://example.com/dm|hiring_manager")
    run(cfg_dir, "touch", "--company", "Harborlight", "--person", "dee-marsh",
        "--path", "cold_hm", "--state", "asked")
    assert run(cfg_dir, "reply", "--company", "Harborlight", "--person", "dee-marsh",
               "--state", "left_company") == 0
    text = (cfg_dir / "network" / "people" / "harborlight.yaml").read_text()
    assert "left_company" in text
    rows = load_touches(cfg_dir / "network" / "touches.csv")
    assert rows[-1].state == "left_company" and rows[-1].path == "cold_hm"


def test_due_appends_no_reply_rows(tmp_path, capsys):
    cfg_dir = _cfg(tmp_path)
    run(cfg_dir, "touch", "--company", "Harborlight", "--person", "ana-rivera",
        "--path", "warm", "--state", "asked", today=datetime.date(2026, 9, 28))
    assert run(cfg_dir, "due", "--dry-run") == 0
    assert len(load_touches(cfg_dir / "network" / "touches.csv")) == 1
    assert run(cfg_dir, "due") == 0
    assert load_touches(cfg_dir / "network" / "touches.csv")[-1].state == "no_reply"
    assert "no_reply" in capsys.readouterr().out


def test_paths_prints_a_table(tmp_path, capsys):
    cfg_dir = _cfg(tmp_path)
    assert run(cfg_dir, "paths", "Harborlight", "Cobalt Grid") == 0
    out = capsys.readouterr().out
    assert "| Harborlight | warm: Ana Rivera, connected 2019 |" in out
    assert "| Cobalt Grid | unresearched |" in out


def test_a_broken_touch_file_is_a_clean_error(tmp_path, capsys):
    cfg_dir = _cfg(tmp_path)
    (cfg_dir / "network" / "touches.csv").write_text("date,company\nx,y\n")
    assert run(cfg_dir, "gate", "Harborlight") == 2
    assert "network:" in capsys.readouterr().out
