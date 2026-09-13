"""The command line: what a run actually does to the filesystem, and what it
refuses to do when something is wrong.

Every fixture here is synthetic — fictional employers for the example persona
(a data engineer), fictional posting URLs under example.com.
"""
import shutil
from pathlib import Path

from engine.radar.cli import main
from tests.fixtures import BDR_JD, make_row

EXAMPLE = Path(__file__).parent.parent / "config.example"


def _config(tmp_path, **settings):
    """A runnable config directory under tmp_path, with settings.yaml lines
    appended or replaced from **settings."""
    cfg_dir = tmp_path / "config"
    shutil.copytree(EXAMPLE, cfg_dir)
    if settings:
        path = cfg_dir / "settings.yaml"
        kept = [line for line in path.read_text().splitlines()
                if line.split(":")[0].strip() not in settings]
        kept += [f"{k}: {v}" for k, v in settings.items()]
        path.write_text("\n".join(kept) + "\n")
    return cfg_dir


def _rows(*companies):
    return [make_row(id=str(i), company=c,
                     job_url=f"https://example.com/jobs/view/{i}")
            for i, c in enumerate(companies, start=1)]


# --- a normal run -----------------------------------------------------------

def test_run_writes_the_day_folder_and_saves_state(tmp_path, capsys):
    cfg_dir = _config(tmp_path)
    rows = _rows("Cobalt Grid") + [
        make_row(id="9", company="Quarry Systems", description=BDR_JD,
                 job_url="https://example.com/jobs/view/9")]

    assert main(["--config", str(cfg_dir)], scrape_fn=lambda cfg: rows) == 0

    day_dirs = list((tmp_path / "radar-out").iterdir())
    assert len(day_dirs) == 1
    queue = (day_dirs[0] / "queue.md").read_text()
    assert "Cobalt Grid" in queue
    assert "Quarry Systems" in queue and "bdr-scope" in queue  # kills stay visible
    assert (day_dirs[0] / "jd").is_dir()
    assert (cfg_dir / "state.json").exists()
    assert "2 raw rows" in capsys.readouterr().out


def test_second_run_skips_rows_already_in_state(tmp_path, capsys):
    cfg_dir = _config(tmp_path)
    rows = _rows("Cobalt Grid")
    main(["--config", str(cfg_dir)], scrape_fn=lambda cfg: rows)
    capsys.readouterr()

    assert main(["--config", str(cfg_dir)], scrape_fn=lambda cfg: rows) == 0
    assert "nothing new" in capsys.readouterr().out


def test_run_suppresses_companies_named_in_the_tracker(tmp_path):
    tracker = tmp_path / "tracker.md"
    tracker.write_text(
        "## Active\n\n| Company | Role |\n|---|---|\n"
        "| Cobalt Grid | Data Engineer |\n\n"
        "## Closed\n\n| Company | Role | Date closed |\n|---|---|---|\n"
        "| Harborlight Data | Data Engineer | 2026-09-01 |\n")
    cfg_dir = _config(tmp_path, tracker="./tracker.md")
    rows = _rows("Cobalt Grid", "Harborlight Data", "Tessellate Labs")

    assert main(["--config", str(cfg_dir)], scrape_fn=lambda cfg: rows) == 0

    queue = next((tmp_path / "radar-out").iterdir()) / "queue.md"
    text = queue.read_text()
    assert "Tessellate Labs" in text
    assert "Cobalt Grid" not in text        # active row
    assert "Harborlight Data" not in text   # closed inside the window


# --- a broken scrape --------------------------------------------------------

def test_zero_rows_is_loud_and_leaves_state_alone(tmp_path, capsys):
    cfg_dir = _config(tmp_path)
    main(["--config", str(cfg_dir)], scrape_fn=lambda cfg: _rows("Cobalt Grid"))
    before = (cfg_dir / "state.json").read_text()
    capsys.readouterr()

    code = main(["--config", str(cfg_dir)], scrape_fn=lambda cfg: [])

    out = capsys.readouterr().out
    assert "SCRAPE RETURNED 0 ROWS" in out
    assert "broken scrape, not a quiet day" in out
    assert code != 0
    assert (cfg_dir / "state.json").read_text() == before


# --- dry run ----------------------------------------------------------------

def test_dry_run_exercises_config_and_pipeline_without_touching_disk(tmp_path, capsys):
    cfg_dir = _config(tmp_path)
    assert main(["--config", str(cfg_dir), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "dry run" in out.lower()
    assert not (tmp_path / "radar-out").exists()
    assert not (cfg_dir / "state.json").exists()


def test_dry_run_never_scrapes(tmp_path):
    def boom(cfg):
        raise AssertionError("dry run must not scrape")

    assert main(["--config", str(_config(tmp_path)), "--dry-run"], scrape_fn=boom) == 0


def test_dry_run_reports_a_broken_config_instead_of_pretending(tmp_path, capsys):
    (tmp_path / "config").mkdir()
    code = main(["--config", str(tmp_path / "config"), "--dry-run"])
    assert code != 0
    assert "config.example" in capsys.readouterr().out


# --- config resolution ------------------------------------------------------

def test_missing_config_names_the_fix(tmp_path, capsys):
    code = main(["--config", str(tmp_path / "nope")])
    assert code != 0
    assert "config.example" in capsys.readouterr().out


def test_config_defaults_to_the_config_dir_beside_you(tmp_path, monkeypatch, capsys):
    _config(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert main([], scrape_fn=lambda cfg: _rows("Cobalt Grid")) == 0
    assert (tmp_path / "radar-out").exists()


# --- liveness check ---------------------------------------------------------

def test_check_classifies_tracked_postings(tmp_path, capsys):
    tracker = tmp_path / "tracker.md"
    tracker.write_text(
        "## Active\n\n| Company | Role | Source |\n|---|---|---|\n"
        "| Cobalt Grid | Data Engineer | (https://example.com/jobs/view/1) |\n"
        "| Quarry Systems | Data Engineer | (https://example.com/jobs/view/2) |\n")
    cfg_dir = _config(tmp_path, tracker="./tracker.md")

    responses = {"https://example.com/jobs/view/1": (200, "Apply now"),
                 "https://example.com/jobs/view/2": (404, "")}
    code = main(["--config", str(cfg_dir), "--check"],
                fetch_fn=lambda url: responses[url])

    out = capsys.readouterr().out
    assert code == 0
    assert "LIVE" in out and "DEAD" in out
    assert "Quarry Systems" in out
    assert "1 live, 1 dead" in out


def test_check_says_so_when_nothing_is_tracked(tmp_path, capsys):
    tracker = tmp_path / "tracker.md"
    tracker.write_text("## Active\n\n| Company | Role |\n|---|---|\n"
                       "| Cobalt Grid | Data Engineer |\n")
    cfg_dir = _config(tmp_path, tracker="./tracker.md")
    assert main(["--config", str(cfg_dir), "--check"], fetch_fn=lambda url: (200, "")) == 0
    assert "nothing to check" in capsys.readouterr().out


def test_check_without_a_tracker_configured_explains_itself(tmp_path, capsys):
    code = main(["--config", str(_config(tmp_path)), "--check"],
                fetch_fn=lambda url: (200, ""))
    assert code != 0
    assert "tracker" in capsys.readouterr().out.lower()


def _no_scrape_module():
    raise ImportError("No module named 'engine.radar.scrape'")


def test_check_reports_a_missing_scrape_module_clearly(tmp_path, capsys, monkeypatch):
    # --check needs the network adapter, which ships with the scrape module. If
    # that module can't be imported, say so plainly rather than dying on a
    # traceback the reader has to decode.
    import engine.radar.cli as cli

    tracker = tmp_path / "tracker.md"
    tracker.write_text("## Active\n\n| Company | Role | Source |\n|---|---|---|\n"
                       "| Cobalt Grid | Data Engineer | (https://example.com/jobs/view/1) |\n")
    cfg_dir = _config(tmp_path, tracker="./tracker.md")
    monkeypatch.setattr(cli, "_scrape_module", _no_scrape_module)

    code = main(["--config", str(cfg_dir), "--check"])
    assert code != 0
    assert "scrape module not yet available" in capsys.readouterr().out


def test_run_reports_a_missing_scrape_module_clearly(tmp_path, capsys, monkeypatch):
    import engine.radar.cli as cli

    cfg_dir = _config(tmp_path)
    monkeypatch.setattr(cli, "_scrape_module", _no_scrape_module)

    code = main(["--config", str(cfg_dir)])
    assert code != 0
    assert "scrape module not yet available" in capsys.readouterr().out
