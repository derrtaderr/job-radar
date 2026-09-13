"""The day's delivery folder: queue.md plus a jd/ file per posting.

Every fixture here is synthetic — fictional employers for the example persona
(a data engineer), fictional posting URLs under example.com.
"""
from engine.radar.report import _comp


def test_comp_range_renders_in_thousands():
    assert _comp({"min_amount": 150000, "max_amount": 190000,
                  "interval": "yearly"}) == "$150-190K"


def test_comp_max_only():
    assert _comp({"min_amount": None, "max_amount": 190000,
                  "interval": "yearly"}) == "to $190K"


def test_comp_min_only():
    assert _comp({"min_amount": 150000, "max_amount": None,
                  "interval": "yearly"}) == "from $150K"


def test_comp_unlisted():
    assert _comp({"min_amount": None, "max_amount": None,
                  "interval": "yearly"}) == "unlisted"


def test_comp_hourly_keeps_the_interval_visible():
    # A non-yearly number must never be silently rendered as a salary band —
    # "$40-60K" for an hourly rate would be a lie the reader can't catch.
    assert _comp({"min_amount": 40, "max_amount": 60,
                  "interval": "hourly"}) == "40-60 hourly"


def test_comp_hourly_single_bound():
    assert _comp({"min_amount": None, "max_amount": 60,
                  "interval": "hourly"}) == "60 hourly"


def test_comp_hourly_unlisted():
    assert _comp({"min_amount": None, "max_amount": None,
                  "interval": "hourly"}) == "unlisted"


def test_comp_interval_absent_defaults_to_yearly_range():
    assert _comp({"min_amount": 100000, "max_amount": 150000,
                  "interval": None}) == "$100-150K"


def test_comp_drops_a_pointless_decimal_on_non_yearly_amounts():
    # Scraped amounts arrive as floats; "40.0-60.0 hourly" is noise.
    assert _comp({"min_amount": 40.0, "max_amount": 60.5,
                  "interval": "hourly"}) == "40-60.5 hourly"
