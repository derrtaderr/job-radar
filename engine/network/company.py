"""Company-name matching between a LinkedIn export and a scraped posting.

Two different authors write these names, so they drift ("Northwind
Analytics, Inc." against "Northwind Analytics"). Normalisation reuses the
decision ledger's `normalise_name`, so the radar has one answer to "are these
the same company".

The match is graded the way DESIGN.md grades evidence. An exact match after
normalisation or an alias is a verdict: the connection is warm. A substring
match is only a flag, because a wrong warm claim costs the person an awkward
message and a flag costs them a glance.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from engine.network.errors import NetworkError
from engine.radar.ledger import normalise_name

# Same floor the tracker matcher uses: below four characters a substring hit
# is noise ("ai" is inside half the companies on a board).
MIN_PARTIAL = 4

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(text) -> str:
    """Lower-case, every run of non-alphanumerics collapsed to one hyphen."""
    return _NON_SLUG.sub("-", str(text or "").lower()).strip("-")


def load_aliases(path) -> dict:
    """{normalised variant: normalised canonical} from aliases.yaml, which maps
    a canonical company name to a list of the names it also goes by. A missing
    file is no aliases, not an error."""
    p = Path(path)
    if not p.exists():
        return {}
    try:
        raw = yaml.safe_load(p.read_text()) or {}
    except yaml.YAMLError as exc:
        raise NetworkError(f"bad yaml in {p}: {exc}") from exc
    if not isinstance(raw, dict):
        raise NetworkError(
            f"{p} must map a company name to a list of the names it also goes by")
    aliases = {}
    for name, variants in raw.items():
        if not isinstance(variants, list) or not all(
                isinstance(v, str) for v in variants):
            raise NetworkError(
                f"{p}: {name!r} must list its other names as a YAML list of strings")
        target = normalise_name(name)
        for variant in variants:
            aliases[normalise_name(variant)] = target
    return aliases


def canonical(name, aliases) -> str:
    """The comparable form of a company name, with aliases applied."""
    normalised = normalise_name(name)
    return aliases.get(normalised, normalised)


def match(left, right, aliases) -> str:
    """'exact', 'partial', or 'none'. Only 'exact' may ever mean warm."""
    a, b = canonical(left, aliases), canonical(right, aliases)
    if not a or not b:
        return "none"
    if a == b:
        return "exact"
    if min(len(a), len(b)) >= MIN_PARTIAL and (a in b or b in a):
        return "partial"
    return "none"


def company_slug(name, aliases) -> str:
    """The filename stem a company's people file is stored under."""
    slug = slugify(canonical(name, aliases))
    if not slug:
        raise NetworkError(
            f"company {name!r} normalises to nothing, so no file can be named after it")
    return slug
