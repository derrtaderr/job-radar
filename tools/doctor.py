#!/usr/bin/env python3
"""doctor — read-only environment and config health check for job-radar.

Eight independent checks, each returning a CheckResult, so a stranger with a
half-set-up machine gets every failure at once instead of one at a time
across eight runs. The doctor never writes anything, anywhere — including
the git config read (check 6). It reads `git config core.hooksPath`, never
sets it; every fix it prints is a command the human runs, not one doctor.py
runs for them.

    python tools/doctor.py [--config DIR]

Exit code is 1 iff any check FAILs. WARN and SKIP never affect it — WARN
means "this half of the tool won't work, the rest is fine" (missing typst,
missing jobspy), SKIP means "this check has nothing to check yet" (no
config/ at all, so checks that need a loaded Config can't run).
"""
from __future__ import annotations

import argparse
import importlib
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):
    # Running as a script (`python tools/doctor.py ...`) rather than
    # imported as `tools.doctor` — put the repo root on sys.path so the
    # cross-package imports below resolve. Same precedent as tracker_cli.py.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.loop.tracker_schema import tracker_check
from engine.profile_schema import check_profile
from engine.radar.config import ConfigError, load_config

MIN_PYTHON = (3, 11)
REQUIRED_PACKAGES = ("pypdf", "yaml")
OPTIONAL_PACKAGES = ("jobspy",)

GITIGNORE_REQUIRED_LINES = (
    "config/",
    "apply-out/",
    "archive/",
    "radar-out/",
    "templates/custom/",
    ".privacy-denylist",
)


@dataclass
class CheckResult:
    """One check's outcome. `ok` is tri/quad-state: True (OK), False (FAIL),
    "warn" (WARN — never affects exit code), or "skip" (SKIP — the check has
    nothing to check yet, also never affects exit code). `fix` is the exact
    command or edit that repairs a failure; empty when there's nothing to
    fix (an OK, or a SKIP with nothing actionable yet)."""

    name: str
    ok: object
    detail: str
    fix: str = ""

    @property
    def status(self) -> str:
        if self.ok is True:
            return "OK"
        if self.ok is False:
            return "FAIL"
        return str(self.ok).upper()


def _importable(name: str) -> bool:
    try:
        importlib.import_module(name)
        return True
    except ImportError:
        return False


# --- individual checks -------------------------------------------------------

def _python_version_info():
    # A thin wrapper around sys.version_info so tests can monkeypatch THIS
    # (via monkeypatch.setattr(doctor, "_python_version_info", ...)) instead
    # of the real sys.version_info — patching the real one breaks any
    # library that reads it at import time (bs4, pulled in transitively by
    # jobspy, is one), which fires mid-test since checks run in-process.
    return sys.version_info


def _check_python_version() -> CheckResult:
    info = _python_version_info()
    version = f"{info[0]}.{info[1]}.{info[2]}"
    ok = tuple(info[:2]) >= MIN_PYTHON
    fix = "" if ok else f"install Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer"
    return CheckResult("python version", ok, f"python {version}", fix)


_VENV_FIX = ".venv/bin/pip install -r requirements.txt -r requirements-dev.txt"


def _check_venv_and_required_packages(repo_root: Path) -> CheckResult:
    venv_dir = repo_root / ".venv"
    if not venv_dir.is_dir():
        return CheckResult(
            "venv + required packages", False,
            f"no .venv/ found at {venv_dir}",
            f"python3 -m venv .venv && {_VENV_FIX}")

    missing = [name for name in REQUIRED_PACKAGES if not _importable(name)]
    if missing:
        return CheckResult(
            "venv + required packages", False,
            f".venv/ present but not importable: {', '.join(missing)}",
            _VENV_FIX)

    return CheckResult(
        "venv + required packages", True,
        f".venv/ present; {', '.join(REQUIRED_PACKAGES)} importable", "")


def _check_jobspy() -> CheckResult:
    if _importable("jobspy"):
        return CheckResult("jobspy", True, "jobspy importable", "")
    return CheckResult(
        "jobspy", "warn",
        "jobspy not importable — the radar (scrape) needs it, "
        "drafting/loop tools don't",
        "pip install python-jobspy")


def _check_typst() -> CheckResult:
    if shutil.which("typst") is not None:
        return CheckResult("typst", True, "typst on PATH", "")
    return CheckResult(
        "typst", "warn",
        "typst not on PATH — drafting (resume/cover-letter compile) needs it",
        "brew install typst")


_CONFIG_FIX = "cp -r config.example config"


def _load_config_or_none(config_dir: Path):
    """Try load_config once and hand back (config, error) — error is the
    ConfigError's message string (never None-and-config-both-set). Checks 5
    and 8 depend on a loaded Config, so they share this instead of each
    calling load_config a second time and risking two different verdicts."""
    try:
        return load_config(config_dir), None
    except ConfigError as exc:
        return None, str(exc)


def _check_config(config_dir: Path, error: "str | None") -> CheckResult:
    if error is None:
        return CheckResult("config", True, f"config loads from {config_dir}", "")
    return CheckResult("config", False, error, _CONFIG_FIX)


def _check_profile(config_dir: Path, config_error: "str | None") -> CheckResult:
    if config_error is not None:
        return CheckResult(
            "profile", "skip",
            "config didn't load — see the 'config' check above", "")

    profile_path = config_dir / "profile.md"
    if not profile_path.exists():
        return CheckResult(
            "profile", False, f"{profile_path} does not exist",
            "cp config.example/profile.md config/profile.md")

    violations = check_profile(profile_path.read_text())
    if violations:
        return CheckResult(
            "profile", False, "; ".join(violations),
            f"edit {profile_path} to add what's missing")

    return CheckResult("profile", True, f"{profile_path} has the required shape", "")


_HOOKS_PATH_FIX = "git config core.hooksPath .githooks"


def _check_privacy_hook(repo_root: Path) -> CheckResult:
    # Read-only: `git config --get` never writes. The doctor's job is to
    # report the fix, never to run it.
    result = subprocess.run(
        ["git", "-C", str(repo_root), "config", "--get", "core.hooksPath"],
        capture_output=True, text=True)
    hooks_path = result.stdout.strip()

    if result.returncode != 0 or not hooks_path:
        return CheckResult(
            "privacy hook", False, "core.hooksPath is not set", _HOOKS_PATH_FIX)
    if hooks_path != ".githooks":
        return CheckResult(
            "privacy hook", False,
            f"core.hooksPath is {hooks_path!r}, expected '.githooks'",
            _HOOKS_PATH_FIX)
    return CheckResult("privacy hook", True, "core.hooksPath is .githooks", "")


def _check_gitignore(repo_root: Path) -> CheckResult:
    gitignore_path = repo_root / ".gitignore"
    if not gitignore_path.exists():
        return CheckResult(
            "gitignore integrity", False,
            f"{gitignore_path} does not exist",
            f"create {gitignore_path} with: " + ", ".join(GITIGNORE_REQUIRED_LINES))

    lines = {line.strip() for line in gitignore_path.read_text().splitlines()}
    missing = [line for line in GITIGNORE_REQUIRED_LINES if line not in lines]
    if missing:
        return CheckResult(
            "gitignore integrity", False,
            f"{gitignore_path} is missing: {', '.join(missing)}",
            f"add to {gitignore_path}: {', '.join(missing)}")

    return CheckResult(
        "gitignore integrity", True,
        f"{gitignore_path} has all {len(GITIGNORE_REQUIRED_LINES)} required lines", "")


# --- orchestration ------------------------------------------------------------

def run_checks(repo_root, config_dir) -> list:
    """Run all eight checks and return their CheckResults, in order. Every
    check runs independently — one failing never skips or hides another,
    except checks 5 and 8, which SKIP (not FAIL) when there's no loadable
    Config to check yet."""
    repo_root = Path(repo_root)
    config_dir = Path(config_dir)
    config, config_error = _load_config_or_none(config_dir)

    return [
        _check_python_version(),
        _check_venv_and_required_packages(repo_root),
        _check_jobspy(),
        _check_typst(),
        _check_config(config_dir, config_error),
        _check_profile(config_dir, config_error),
        _check_privacy_hook(repo_root),
        _check_gitignore(repo_root),
    ]
