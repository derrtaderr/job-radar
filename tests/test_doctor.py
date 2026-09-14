"""tools/doctor.py — the environment doctor. Eight independent checks over a
repo + config directory, each returning a CheckResult so one failure never
hides another. Read-only end to end, including the git config read (check 6)
— the doctor diagnoses, it never repairs.

Every check here runs against a synthetic repo under tmp_path or a
monkeypatched piece of the real environment (shutil.which, sys.modules,
sys.version_info) — never the developer machine's actual global state, so
this suite is honest whether or not typst/jobspy/a real git hook happen to be
installed on whoever runs it.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tools import doctor

EXAMPLE = Path(__file__).parent.parent / "config.example"


def _git_repo(tmp_path, hooks_path=".githooks", gitignore_lines=None):
    """A minimal git repo under tmp_path with the doctor's expected shape:
    .githooks/ present, core.hooksPath set (unless hooks_path is None), and
    a .gitignore carrying the real repo's privacy lines (unless overridden)."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    if hooks_path is not None:
        subprocess.run(
            ["git", "config", "core.hooksPath", hooks_path],
            cwd=tmp_path, check=True)
    if gitignore_lines is None:
        gitignore_lines = list(doctor.GITIGNORE_REQUIRED_LINES)
    (tmp_path / ".gitignore").write_text("\n".join(gitignore_lines) + "\n")
    return tmp_path


def _config_dir(tmp_path):
    cfg_dir = tmp_path / "config"
    shutil.copytree(EXAMPLE, cfg_dir)
    return cfg_dir


def _result(results, name):
    matches = [r for r in results if r.name == name]
    assert len(matches) == 1, f"expected exactly one {name!r} result, got {matches}"
    return matches[0]


# --- CheckResult shape -------------------------------------------------------

def test_check_result_status_reports_ok_warn_fail():
    assert doctor.CheckResult("x", True, "d", "").status == "OK"
    assert doctor.CheckResult("x", False, "d", "").status == "FAIL"
    assert doctor.CheckResult("x", "warn", "d", "").status == "WARN"
    assert doctor.CheckResult("x", "skip", "d", "").status == "SKIP"


# --- check 1: python version -------------------------------------------------

def test_python_version_ok_on_a_modern_interpreter(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor.sys, "version_info", (3, 12, 4, "final", 0))
    repo = _git_repo(tmp_path)
    results = doctor.run_checks(repo, _config_dir(tmp_path))
    result = _result(results, "python version")
    assert result.ok is True
    assert "3.12" in result.detail


def test_python_version_fails_below_3_11(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor.sys, "version_info", (3, 10, 9, "final", 0))
    repo = _git_repo(tmp_path)
    results = doctor.run_checks(repo, _config_dir(tmp_path))
    result = _result(results, "python version")
    assert result.ok is False
    assert result.fix
