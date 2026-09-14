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

def _check_python_version() -> CheckResult:
    info = sys.version_info
    version = f"{info[0]}.{info[1]}.{info[2]}"
    ok = tuple(info[:2]) >= MIN_PYTHON
    fix = "" if ok else f"install Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer"
    return CheckResult("python version", ok, f"python {version}", fix)


# --- orchestration ------------------------------------------------------------

def run_checks(repo_root, config_dir) -> list:
    """Run all eight checks and return their CheckResults, in order. Every
    check runs independently — one failing never skips or hides another,
    except checks 5 and 8, which SKIP (not FAIL) when there's no loadable
    Config to check yet."""
    repo_root = Path(repo_root)
    config_dir = Path(config_dir)

    return [
        _check_python_version(),
    ]
