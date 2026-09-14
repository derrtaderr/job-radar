"""tools/doctor.py — the environment doctor. Nine independent checks over a
repo + config directory, each returning a CheckResult so one failure never
hides another. Read-only end to end, including the git config read (check 7)
— the doctor diagnoses, it never repairs.

The check numbers in the section comments below are positions in
`run_checks`'s returned list, in order, so a reader can map a comment to the
line of `doctor.py` output it covers.

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

from tests.fixtures_tracker import VALID_TRACKER
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


def _configure_tracker(cfg_dir, rel_path: str) -> None:
    """Point settings.yaml's `tracker:` key at rel_path (resolved against
    cfg_dir.parent, same as load_config)."""
    settings = cfg_dir / "settings.yaml"
    kept = [line for line in settings.read_text().splitlines()
            if not line.startswith("tracker:")]
    kept.append(f"tracker: {rel_path}")
    settings.write_text("\n".join(kept) + "\n")


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
    monkeypatch.setattr(doctor, "_python_version_info", lambda: (3, 12, 4, "final", 0))
    repo = _git_repo(tmp_path)
    results = doctor.run_checks(repo, _config_dir(tmp_path))
    result = _result(results, "python version")
    assert result.ok is True
    assert "3.12" in result.detail


def test_python_version_fails_below_3_11(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "_python_version_info", lambda: (3, 10, 9, "final", 0))
    repo = _git_repo(tmp_path)
    results = doctor.run_checks(repo, _config_dir(tmp_path))
    result = _result(results, "python version")
    assert result.ok is False
    assert result.fix


# --- check 2: venv + required packages -------------------------------------

def test_venv_and_required_packages_ok_when_venv_dir_present_and_importable(tmp_path):
    (tmp_path / ".venv").mkdir()
    repo = _git_repo(tmp_path)
    results = doctor.run_checks(repo, _config_dir(tmp_path))
    result = _result(results, "venv + required packages")
    assert result.ok is True


def test_venv_missing_is_a_fail_with_a_create_command(tmp_path):
    repo = _git_repo(tmp_path)  # no .venv/ created
    results = doctor.run_checks(repo, _config_dir(tmp_path))
    result = _result(results, "venv + required packages")
    assert result.ok is False
    assert ".venv" in result.fix


def test_missing_required_package_fails_and_names_it(tmp_path, monkeypatch):
    (tmp_path / ".venv").mkdir()
    monkeypatch.setitem(sys.modules, "yaml", None)  # simulate absence
    repo = _git_repo(tmp_path)
    results = doctor.run_checks(repo, _config_dir(tmp_path))
    result = _result(results, "venv + required packages")
    assert result.ok is False
    assert "yaml" in result.detail


# --- check 3: jobspy importable (WARN) ---------------------------------------

def test_jobspy_present_is_ok(tmp_path, monkeypatch):
    fake_jobspy = type(sys)("jobspy")
    monkeypatch.setitem(sys.modules, "jobspy", fake_jobspy)  # simulate presence
    (tmp_path / ".venv").mkdir()
    repo = _git_repo(tmp_path)
    results = doctor.run_checks(repo, _config_dir(tmp_path))
    result = _result(results, "jobspy")
    assert result.ok is True


def test_jobspy_absent_warns_not_fails(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "jobspy", None)  # simulate absence
    (tmp_path / ".venv").mkdir()
    repo = _git_repo(tmp_path)
    results = doctor.run_checks(repo, _config_dir(tmp_path))
    result = _result(results, "jobspy")
    assert result.ok == "warn"
    assert result.status == "WARN"


# --- check 4: typst on PATH (WARN) -------------------------------------------

def test_typst_present_is_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/opt/homebrew/bin/typst")
    repo = _git_repo(tmp_path)
    results = doctor.run_checks(repo, _config_dir(tmp_path))
    result = _result(results, "typst")
    assert result.ok is True


def test_typst_absent_warns_with_brew_fix(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    repo = _git_repo(tmp_path)
    results = doctor.run_checks(repo, _config_dir(tmp_path))
    result = _result(results, "typst")
    assert result.ok == "warn"
    assert result.fix == "brew install typst"


# --- check 5: config/ exists and load_config succeeds -----------------------

def test_config_ok_when_config_example_copied_verbatim(tmp_path):
    repo = _git_repo(tmp_path)
    results = doctor.run_checks(repo, _config_dir(tmp_path))
    result = _result(results, "config")
    assert result.ok is True


def test_config_fails_with_cp_fix_when_config_dir_missing_entirely(tmp_path):
    repo = _git_repo(tmp_path)
    missing_dir = tmp_path / "config"  # never created
    results = doctor.run_checks(repo, missing_dir)
    result = _result(results, "config")
    assert result.ok is False
    assert result.fix == "cp -r config.example config"


def test_config_surfaces_configerror_message_verbatim(tmp_path):
    repo = _git_repo(tmp_path)
    cfg_dir = _config_dir(tmp_path)
    (cfg_dir / "settings.yaml").write_text("not: valid: yaml: [")
    results = doctor.run_checks(repo, cfg_dir)
    result = _result(results, "config")
    assert result.ok is False
    assert "bad yaml in settings.yaml" in result.detail


def test_config_fix_is_edit_not_cp_when_config_dir_exists_but_a_value_is_bad(tmp_path):
    # `cp -r config.example config` under a POPULATED config/ destroys real
    # judgment (kill rules, comp floor, claim ledger) that no `git checkout`
    # brings back. That fix line is only correct when config/ never existed —
    # once it exists, the fix is editing the file the error already names.
    repo = _git_repo(tmp_path)
    cfg_dir = _config_dir(tmp_path)
    (cfg_dir / "settings.yaml").write_text("not: valid: yaml: [")
    results = doctor.run_checks(repo, cfg_dir)
    result = _result(results, "config")
    assert result.ok is False
    assert result.fix == "edit the file named in the error above"


# --- check 6: profile.md schema (reuses engine.profile_schema) --------------

def test_profile_ok_when_config_example_copied_verbatim(tmp_path):
    repo = _git_repo(tmp_path)
    results = doctor.run_checks(repo, _config_dir(tmp_path))
    result = _result(results, "profile")
    assert result.ok is True


def test_profile_skips_when_config_does_not_load_at_all(tmp_path):
    repo = _git_repo(tmp_path)
    missing_dir = tmp_path / "config"  # never created — check 5 FAILs
    results = doctor.run_checks(repo, missing_dir)
    result = _result(results, "profile")
    assert result.ok == "skip"
    assert result.status == "SKIP"


def test_profile_fails_when_missing_even_though_config_loads(tmp_path):
    repo = _git_repo(tmp_path)
    cfg_dir = _config_dir(tmp_path)
    (cfg_dir / "profile.md").unlink()  # profile.md isn't in load_config's
    # REQUIRED_FILES, so config still loads fine with it gone
    results = doctor.run_checks(repo, cfg_dir)
    assert _result(results, "config").ok is True
    result = _result(results, "profile")
    assert result.ok is False


def test_profile_fails_and_names_violations_when_malformed(tmp_path):
    repo = _git_repo(tmp_path)
    cfg_dir = _config_dir(tmp_path)
    (cfg_dir / "profile.md").write_text("---\nname: Alex\n---\nno sections here")
    results = doctor.run_checks(repo, cfg_dir)
    result = _result(results, "profile")
    assert result.ok is False
    assert "missing keys" in result.detail


# --- check 7: privacy hook active (git config core.hooksPath, read-only) ----

def test_hook_ok_when_hookspath_set_to_githooks(tmp_path):
    repo = _git_repo(tmp_path, hooks_path=".githooks")
    results = doctor.run_checks(repo, _config_dir(tmp_path))
    result = _result(results, "privacy hook")
    assert result.ok is True


def test_hook_fails_with_exact_set_command_when_unset(tmp_path):
    repo = _git_repo(tmp_path, hooks_path=None)
    results = doctor.run_checks(repo, _config_dir(tmp_path))
    result = _result(results, "privacy hook")
    assert result.ok is False
    assert result.fix == "git config core.hooksPath .githooks"


def test_hook_fails_when_set_to_something_else(tmp_path):
    repo = _git_repo(tmp_path, hooks_path="some/other/dir")
    results = doctor.run_checks(repo, _config_dir(tmp_path))
    result = _result(results, "privacy hook")
    assert result.ok is False
    assert "some/other/dir" in result.detail


def test_hook_check_never_writes_git_config(tmp_path):
    repo = _git_repo(tmp_path, hooks_path=None)
    doctor.run_checks(repo, _config_dir(tmp_path))
    result = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=repo, capture_output=True, text=True)
    assert result.returncode != 0  # still unset — doctor never set it


# --- check 8: gitignore integrity --------------------------------------------

def test_gitignore_ok_when_every_required_line_present(tmp_path):
    repo = _git_repo(tmp_path)  # writes all GITIGNORE_REQUIRED_LINES
    results = doctor.run_checks(repo, _config_dir(tmp_path))
    result = _result(results, "gitignore integrity")
    assert result.ok is True


def test_gitignore_fails_and_names_the_exact_missing_line(tmp_path):
    lines = [l for l in doctor.GITIGNORE_REQUIRED_LINES if l != "archive/"]
    repo = _git_repo(tmp_path, gitignore_lines=lines)
    results = doctor.run_checks(repo, _config_dir(tmp_path))
    result = _result(results, "gitignore integrity")
    assert result.ok is False
    assert "archive/" in result.detail


def test_gitignore_fails_naming_every_missing_line_when_several_gone(tmp_path):
    repo = _git_repo(tmp_path, gitignore_lines=["config/"])
    results = doctor.run_checks(repo, _config_dir(tmp_path))
    result = _result(results, "gitignore integrity")
    assert result.ok is False
    for line in doctor.GITIGNORE_REQUIRED_LINES:
        if line != "config/":
            assert line in result.detail


def test_gitignore_fails_when_file_does_not_exist(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    results = doctor.run_checks(tmp_path, _config_dir(tmp_path))
    result = _result(results, "gitignore integrity")
    assert result.ok is False


# --- check 9: tracker check (only when tracker: is configured) --------------

def test_tracker_skips_when_not_configured(tmp_path):
    # config.example's settings.yaml ships `tracker: null`
    repo = _git_repo(tmp_path)
    results = doctor.run_checks(repo, _config_dir(tmp_path))
    result = _result(results, "tracker")
    assert result.ok == "skip"


def test_tracker_skips_when_config_does_not_load_at_all(tmp_path):
    repo = _git_repo(tmp_path)
    missing_dir = tmp_path / "config"  # never created — check 5 FAILs
    results = doctor.run_checks(repo, missing_dir)
    result = _result(results, "tracker")
    assert result.ok == "skip"


def test_tracker_ok_when_configured_and_valid(tmp_path):
    cfg_dir = _config_dir(tmp_path)
    _configure_tracker(cfg_dir, "./tracker.md")
    (tmp_path / "tracker.md").write_text(VALID_TRACKER)
    repo = _git_repo(tmp_path)
    results = doctor.run_checks(repo, cfg_dir)
    result = _result(results, "tracker")
    assert result.ok is True


def test_tracker_fails_and_surfaces_violations_when_configured_but_broken(tmp_path):
    cfg_dir = _config_dir(tmp_path)
    _configure_tracker(cfg_dir, "./tracker.md")
    (tmp_path / "tracker.md").write_text("## Active\nno table here\n")
    repo = _git_repo(tmp_path)
    results = doctor.run_checks(repo, cfg_dir)
    result = _result(results, "tracker")
    assert result.ok is False
    assert "missing required section" in result.detail
    assert "Closed" in result.detail


def test_tracker_fails_when_configured_but_file_missing(tmp_path):
    cfg_dir = _config_dir(tmp_path)
    _configure_tracker(cfg_dir, "./tracker.md")  # never written
    repo = _git_repo(tmp_path)
    results = doctor.run_checks(repo, cfg_dir)
    result = _result(results, "tracker")
    assert result.ok is False


# --- CLI: python tools/doctor.py [--config DIR] ------------------------------

def test_cli_prints_one_line_per_check_and_exits_0_when_all_ok(tmp_path, capsys):
    (tmp_path / ".venv").mkdir()
    repo = _git_repo(tmp_path)
    cfg_dir = _config_dir(tmp_path)

    exit_code = doctor.main(["--config", str(cfg_dir)], repo_root=repo)

    out = capsys.readouterr().out
    assert exit_code == 0
    for name in (
        "python version", "venv + required packages", "jobspy", "typst",
        "config", "profile", "privacy hook", "gitignore integrity", "tracker",
    ):
        assert name in out


def test_cli_exits_1_when_any_check_fails(tmp_path, capsys):
    (tmp_path / ".venv").mkdir()
    repo = _git_repo(tmp_path, hooks_path=None)  # privacy hook FAILs
    cfg_dir = _config_dir(tmp_path)

    exit_code = doctor.main(["--config", str(cfg_dir)], repo_root=repo)

    assert exit_code == 1
    assert "FAIL" in capsys.readouterr().out


def test_cli_warn_never_flips_the_exit_code(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)  # typst WARNs
    (tmp_path / ".venv").mkdir()
    repo = _git_repo(tmp_path)
    cfg_dir = _config_dir(tmp_path)

    exit_code = doctor.main(["--config", str(cfg_dir)], repo_root=repo)

    out = capsys.readouterr().out
    assert "WARN" in out
    assert exit_code == 0


def test_cli_runs_meaningfully_with_no_config_dir_at_all(tmp_path, capsys):
    (tmp_path / ".venv").mkdir()
    repo = _git_repo(tmp_path)
    missing_dir = tmp_path / "config"  # never created

    exit_code = doctor.main(["--config", str(missing_dir)], repo_root=repo)

    out = capsys.readouterr().out
    assert exit_code == 1  # check 5 FAILs
    assert "cp -r config.example config" in out
    assert "SKIP" in out  # checks 6 (profile) and 9 (tracker)
    # every other check still ran and printed
    for name in ("python version", "venv + required packages", "jobspy",
                 "typst", "privacy hook", "gitignore integrity"):
        assert name in out


def test_cli_defaults_config_dir_to_repo_root_slash_config(tmp_path):
    (tmp_path / ".venv").mkdir()
    repo = _git_repo(tmp_path)
    _config_dir(tmp_path)  # lands at tmp_path / "config", the default

    exit_code = doctor.main([], repo_root=repo)

    assert exit_code == 0
