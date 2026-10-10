"""Company matching and business-day math for the warm path. Fictional
companies only."""
import datetime

import pytest

from engine.network.company import (
    canonical, company_slug, load_aliases, match, slugify)
from engine.network.dates import add_business_days
from engine.network.errors import NetworkError

D = datetime.date


def test_business_days_skip_the_weekend():
    assert add_business_days(D(2026, 10, 5), 3) == D(2026, 10, 8)   # Mon -> Thu
    assert add_business_days(D(2026, 10, 9), 3) == D(2026, 10, 14)  # Fri -> Wed
    assert add_business_days(D(2026, 10, 10), 1) == D(2026, 10, 12)  # Sat -> Mon
    assert add_business_days(D(2026, 10, 9), 0) == D(2026, 10, 9)


def test_suffix_and_punctuation_drift_is_an_exact_match():
    assert match("Northwind Analytics, Inc.", "Northwind Analytics", {}) == "exact"
    assert match("COBALT GRID LLC", "Cobalt Grid", {}) == "exact"


def test_substring_is_only_partial_and_floored_at_four_characters():
    assert match("Cobalt Grid Cloud", "Cobalt Grid", {}) == "partial"
    assert match("Abc", "Abc Labs", {}) == "none"
    assert match("Harborlight", "Quarry Systems", {}) == "none"
    assert match("", "Quarry Systems", {}) == "none"


def test_aliases_make_a_variant_exact(tmp_path):
    path = tmp_path / "aliases.yaml"
    path.write_text("Harborlight:\n  - Harborlight Holdings\n  - HL Group\n")
    aliases = load_aliases(path)
    assert match("HL Group", "Harborlight", aliases) == "exact"
    assert canonical("Harborlight Holdings", aliases) == "harborlight"


def test_missing_aliases_file_is_empty(tmp_path):
    assert load_aliases(tmp_path / "nope.yaml") == {}


def test_bad_aliases_file_names_itself(tmp_path):
    path = tmp_path / "aliases.yaml"
    path.write_text("Harborlight: not-a-list\n")
    with pytest.raises(NetworkError, match="aliases.yaml"):
        load_aliases(path)


def test_slugs():
    assert company_slug("Northwind Analytics, Inc.", {}) == "northwind-analytics"
    assert slugify("A. Rivera") == "a-rivera"
    with pytest.raises(NetworkError):
        company_slug(",,,", {})
