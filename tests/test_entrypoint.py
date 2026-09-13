"""The repo-root entry point. It exists so `python3 radar.py` works from a
fresh clone; it must carry no logic of its own."""
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent


def test_entry_point_runs_a_dry_run_from_the_repo_root(tmp_path):
    shutil.copytree(REPO / "config.example", tmp_path / "config")
    result = subprocess.run(
        [sys.executable, str(REPO / "radar.py"), "--config", str(tmp_path / "config"),
         "--dry-run"],
        cwd=REPO, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "dry run" in result.stdout.lower()


def test_entry_point_exits_nonzero_on_a_missing_config(tmp_path):
    result = subprocess.run(
        [sys.executable, str(REPO / "radar.py"), "--config", str(tmp_path / "nope")],
        cwd=REPO, capture_output=True, text=True)
    assert result.returncode != 0
    assert "config.example" in result.stdout


def test_entry_point_shows_help_without_importing_the_network_layer():
    result = subprocess.run(
        [sys.executable, str(REPO / "radar.py"), "--help"],
        cwd=REPO, capture_output=True, text=True)
    assert result.returncode == 0
    assert "--dry-run" in result.stdout and "--check" in result.stdout
