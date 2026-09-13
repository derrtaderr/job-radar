from pathlib import Path

from engine.radar.config import load_config
from engine.radar.rules_engine import title_passes, kill_flags
from tests.fixtures import make_row, BDR_JD, QUOTA_DESIGN_JD, MANAGER_JD, MENTOR_JD

CFG = load_config(Path(__file__).parent.parent / "config.example")


def _names(row):
    return [n for n, _ in kill_flags(row, CFG)]


def test_title_keep_and_drop():
    assert title_passes("Senior Data Engineer", CFG)
    assert not title_passes("Data Engineering Intern", CFG)
    assert not title_passes("Backend Engineer", CFG)


def test_bdr_true_positive_quotes_evidence():
    flags = kill_flags(make_row(description=BDR_JD + " Fully remote."), CFG)
    assert ("bdr-scope" in [n for n, _ in flags])
    assert "quota" in dict(flags)["bdr-scope"]


def test_quota_design_near_miss_survives():
    assert "bdr-scope" not in _names(make_row(description=QUOTA_DESIGN_JD + " Fully remote."))


def test_manager_true_positive_and_mentor_near_miss():
    assert "not-ic" in _names(make_row(description=MANAGER_JD + " Fully remote."))
    assert "not-ic" not in _names(make_row(description=MENTOR_JD + " Fully remote."))


def test_clean_row_has_no_flags():
    assert _names(make_row()) == []
