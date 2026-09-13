import datetime
from pathlib import Path

from engine.radar.config import load_config
from engine.radar.rules_engine import score, posting_status
from tests.fixtures import make_row

CFG = load_config(Path(__file__).parent.parent / "config.example")
TODAY = datetime.date(2026, 9, 13)


def test_top_tier_title_beats_lower_tier():
    top = score(make_row(title="Data Platform Engineer"), TODAY, CFG)
    lower = score(make_row(title="Analytics Engineer"), TODAY, CFG)
    assert top > lower
    assert top == 68   # 30 (tier) + 8 (unlisted comp) + 20 (fresh, age 3) + 10 (remote)
    assert lower == 53  # 15 (tier) + 8 + 20 + 10


def test_comp_at_target_adds_target_comp_pts():
    row = make_row(title="Data Platform Engineer", max_amount=200000)
    assert score(row, TODAY, CFG) == 80  # 30 + 20 (target) + 20 (fresh) + 10 (remote)


def test_comp_at_floor_adds_floor_comp_pts():
    row = make_row(title="Data Platform Engineer", max_amount=150000)
    assert score(row, TODAY, CFG) == 75  # 30 + 15 (floor) + 20 (fresh) + 10 (remote)


def test_unlisted_comp_adds_unlisted_comp_pts():
    row = make_row(title="Data Platform Engineer", max_amount=None)
    assert score(row, TODAY, CFG) == 68  # 30 + 8 (unlisted) + 20 (fresh) + 10 (remote)


def test_fresh_posting_beats_old_posting():
    fresh = score(make_row(title="Data Platform Engineer", date_posted="2026-09-11"), TODAY, CFG)
    old = score(make_row(title="Data Platform Engineer", date_posted="2026-09-03"), TODAY, CFG)
    assert fresh == 68  # 30 + 8 + 20 (fresh, age 2) + 10 (remote)
    assert old == 53    # 30 + 8 + 5 (old, age 10) + 10 (remote)


def test_week_old_posting_gets_week_pts():
    row = make_row(title="Data Platform Engineer", date_posted="2026-09-08")  # age 5
    assert score(row, TODAY, CFG) == 60  # 30 + 8 + 12 (week) + 10 (remote)


def test_missing_date_posted_treated_as_14_days_old():
    row = make_row(title="Data Platform Engineer", date_posted=None)
    assert score(row, TODAY, CFG) == 53  # 30 + 8 + 5 (old, age 14) + 10 (remote)


def test_is_remote_adds_remote_pts():
    remote = score(make_row(title="Data Platform Engineer", is_remote=True), TODAY, CFG)
    onsite = score(make_row(title="Data Platform Engineer", is_remote=False), TODAY, CFG)
    assert remote == 68  # 30 + 8 + 20 + 10 (remote)
    assert onsite == 58  # 30 + 8 + 20 + 0


def test_seniority_pattern_adds_seniority_pts():
    senior = score(make_row(title="Staff Data Platform Engineer"), TODAY, CFG)
    plain = score(make_row(title="Data Platform Engineer"), TODAY, CFG)
    assert senior == 76  # 30 (tier) + 8 (seniority) + 8 (unlisted) + 20 (fresh) + 10 (remote)
    assert plain == 68


def test_posting_status_404_is_dead():
    assert posting_status(404, "") == "dead"


def test_posting_status_410_is_dead():
    assert posting_status(410, "") == "dead"


def test_posting_status_200_closed_phrase_is_dead():
    assert posting_status(200, "This role is no longer accepting applications.") == "dead"


def test_posting_status_200_clean_body_is_live():
    assert posting_status(200, "We are hiring a Data Platform Engineer.") == "live"


def test_posting_status_429_is_unknown():
    assert posting_status(429, "") == "unknown"


def test_posting_status_none_is_unknown():
    assert posting_status(None, None) == "unknown"
