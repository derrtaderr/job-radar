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

import functools
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


def normalise_location(value) -> str:
    """One canonical spelling for a location string.

    Lower-cased, country suffix dropped, each comma-separated part mapped from a
    full state name to its abbreviation, and repeated parts collapsed — so
    "New York, United States", "New York, NY", "New York" and "NY" all come back
    as `ny`, and the location rule can no longer resolve one place two ways in
    one run.
    """
    raw = _COUNTRY_SUFFIX.sub("", str(value or ""))
    parts = []
    for part in raw.split(","):
        part = re.sub(r"\s+", " ", part).strip().lower()
        if not part:
            continue
        part = STATES.get(part, part)
        if part not in parts:
            parts.append(part)
    return ", ".join(parts)


# A pattern is a plain list of place names only if it carries no regex syntax
# beyond the `|` that separates entries. Anything else (a character class, a
# quantifier, an escape) cannot be split into entries and normalised without
# changing what it means.
_PLAIN_ALTERNATION = re.compile(r"^[^\\^$.|?*+()\[\]{}]+(?:\|[^\\^$.|?*+()\[\]{}]+)*$")


@functools.lru_cache(maxsize=256)
def _normalised_alternation(source: str):
    """The allowlist pattern with each of its entries normalised, or None when the
    pattern is not a plain list of names.

    Normalising only the LOCATION broke the other side of the comparison: an
    allowlist written as a full state name ("Colorado") used to substring-match
    "Denver, Colorado" and stopped matching once the location normalised to
    `denver, co`. Both sides have to go through the same function, or the fix for
    one spelling becomes a regression for another.
    """
    if not _PLAIN_ALTERNATION.match(source):
        return None
    entries = []
    for entry in source.split("|"):
        entry = normalise_location(entry)
        if entry and entry not in entries:
            entries.append(entry)
    if not entries:
        return None
    # Entries are literals now, so they are escaped rather than re-compiled as
    # patterns — a name containing punctuation must match itself, not be read as
    # syntax.
    return re.compile("|".join(re.escape(e) for e in entries), re.I)


def pattern_matches_location(pattern, value) -> bool:
    """Does a commute-allowlist pattern match this location?

    Matched against the NORMALISED parts of the location, with the pattern's own
    entries normalised the same way, and only on word boundaries — never as a bare
    substring of the raw string. A pattern of `NY` substring-matches
    "Pennsylvania, United States" (…syl-VA-nia) while missing "New York, United
    States" entirely, which is one spelling of a place passing and another
    spelling of the same place being killed in one run. Word-bounded matching on
    normalised parts rejects `pennsylvania` and accepts `ny`, and still accepts a
    pattern of `Denver` against a part reading `denver tech center`, which an
    exact full-match would have broken.
    """
    if not pattern:
        return False
    # The pattern as written, and — when it is a plain list of names — the same
    # list with every entry normalised. Both are tried, so `CO`, `Colorado` and
    # `Denver` all keep matching "Denver, Colorado".
    candidates = [pattern]
    normalised = _normalised_alternation(pattern.pattern)
    if normalised is not None:
        candidates.append(normalised)

    for part in normalise_location(value).split(", "):
        if not part:
            continue
        for candidate in candidates:
            for m in candidate.finditer(part):
                before = part[m.start() - 1] if m.start() else ""
                after = part[m.end()] if m.end() < len(part) else ""
                if not _is_word_char(before) and not _is_word_char(after):
                    return True
    return False


def _is_word_char(ch: str) -> bool:
    return bool(ch) and (ch.isalnum() or ch == "_")
