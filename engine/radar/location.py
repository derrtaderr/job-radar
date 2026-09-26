"""Location text, normalised once so it cannot resolve two ways.

Postings write the same place four different ways — "New York, United States",
"New York, NY", "New York", "NY" — and every consumer that matched those strings
by hand got a different answer. This module is the single normaliser, so every consumer reads one canonical
spelling instead of each inventing its own.

The US state table lives here because more than one consumer needs it:
`strip_territory` removes state and territory tokens from body text before it is
fingerprinted, and the location rule matches a commute allowlist against the
same table's canonical spellings.
"""
from __future__ import annotations

import re

# Full name → USPS abbreviation. DC is included because postings write it as a
# state; the territories are not, because a posting that says "Puerto Rico"
# means something a commute allowlist should be allowed to treat separately.
STATES = {
    "alabama": "al", "alaska": "ak", "arizona": "az", "arkansas": "ar",
    "california": "ca", "colorado": "co", "connecticut": "ct", "delaware": "de",
    "district of columbia": "dc", "florida": "fl", "georgia": "ga",
    "hawaii": "hi", "idaho": "id", "illinois": "il", "indiana": "in",
    "iowa": "ia", "kansas": "ks", "kentucky": "ky", "louisiana": "la",
    "maine": "me", "maryland": "md", "massachusetts": "ma", "michigan": "mi",
    "minnesota": "mn", "mississippi": "ms", "missouri": "mo", "montana": "mt",
    "nebraska": "ne", "nevada": "nv", "new hampshire": "nh",
    "new jersey": "nj", "new mexico": "nm", "new york": "ny",
    "north carolina": "nc", "north dakota": "nd", "ohio": "oh",
    "oklahoma": "ok", "oregon": "or", "pennsylvania": "pa",
    "rhode island": "ri", "south carolina": "sc", "south dakota": "sd",
    "tennessee": "tn", "texas": "tx", "utah": "ut", "vermont": "vt",
    "virginia": "va", "washington": "wa", "west virginia": "wv",
    "wisconsin": "wi", "wyoming": "wy",
}

ABBREVIATIONS = frozenset(STATES.values())

# Longest first, so "west virginia" is consumed before "virginia" would eat
# half of it and leave a stray "west" behind.
_STATE_NAMES = sorted(STATES, key=len, reverse=True)
_STATE_NAME_RE = re.compile(r"\b(?:" + "|".join(_STATE_NAMES) + r")\b", re.I)

# A trailing country, in the spellings job boards actually use.
_COUNTRY_SUFFIX = re.compile(
    r"\s*,\s*(?:united states(?: of america)?|u\.?s\.?a\.?|u\.?s\.?)\s*(?=$|[,.;])",
    re.I)

# "Eastern US", "West Coast", "Central region" — the token that makes one req
# look like two postings.
_TERRITORY = re.compile(
    r"\b(?:eastern|western|central|northern|southern|north|south|east|west|mid)"
    r"[\s-]*(?:us|u\.s\.|usa|united states|coast|region|territory|territories)\b",
    re.I)

# A state abbreviation is only stripped from body text when it follows a comma
# and is upper-case ("based in Denver, CO"). Matching bare two-letter tokens
# case-insensitively would delete the English words "in", "or", "me", "hi",
# "ok", "de", "la", "ma", "pa" and "id" out of every posting.
_ABBREV_AFTER_COMMA = re.compile(
    r"\s*,\s*(" + "|".join(a.upper() for a in sorted(ABBREVIATIONS)) + r")\b")


def strip_territory(text: str) -> str:
    """Remove country suffixes, state tokens and compass-territory phrases from
    free text, so two postings that differ only in which slice of the map they
    name read as the same text."""
    t = str(text or "")
    t = _COUNTRY_SUFFIX.sub("", t)
    t = _ABBREV_AFTER_COMMA.sub("", t)
    t = _STATE_NAME_RE.sub("", t)
    t = _TERRITORY.sub("", t)
    return t
