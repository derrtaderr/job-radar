"""Rules engine — title filter and kill-flag evaluation. Config-driven: the
engine has no opinions of its own, it just runs the judgment that lives in
Config (title_keep/title_drop, kill_rules, and — from Tasks 6/7 — comp_floor
and commute_pattern) against a JobSpy-shaped row.
"""
from __future__ import annotations

import datetime
import re
from typing import Optional

from engine.radar.location import pattern_matches_location

_COMP_CONTEXT = re.compile(r"salary|compensation|base pay|pay range|\bcomp\b|\bOTE\b", re.I)
_MONEY = re.compile(r"\$?\s?(\d{2,3})(?:,(\d{3}))?\s?(k\b)?", re.I)

# Ported verbatim from OLD/rules.py (lines 55-78) — generic engine constants for
# detecting affirmative remote language in a JD while skipping negated mentions.
# Split in two, because the two halves carry different weight and the tightened
# override has to tell them apart (R64-05).
#
# STRONG is a claim about THE ROLE: "fully remote", "remote-first", "remote
# position". A posting that says one of these and then mentions an office in the
# same breath is a remote role with an office, which is ordinary.
#
# WEAK is a mention of remote work without claiming the role is remote: "work from
# home", "working remotely", "#li-remote". This is exactly the vocabulary a HYBRID
# posting uses when it lists which days are which — "Tuesdays and Fridays are
# remote/work from home days" — so a weak mention is the one that loses to hybrid
# phrasing beside it.
_REMOTE_STRONG = re.compile(
    r"fully remote|100 ?% remote|remote[- ]first|remote[- ]eligible"
    r"|fully distributed"
    r"|remote (?:position|role|opportunity|job)"
    r"|work from anywhere"
    r"|remote \((?:us|usa|united states|anywhere)"
    r"|(?:us|u\.s\.|usa)[- ]remote"
    r"|remote,? (?:us\b|usa\b|united states)", re.I)

_REMOTE_WEAK = re.compile(
    r"remote[- ]friendly"
    r"|work from home|work(?:ing)? remotely"
    r"|#li[- ]remote"
    r"|open to remote", re.I)

# The union, kept as one name for the untightened detector the calibrator uses.
_REMOTE_OK = re.compile(_REMOTE_STRONG.pattern + "|" + _REMOTE_WEAK.pattern, re.I)

# Any mention of remote work at all, however weak. Used to spot a posting that is
# OFFERING remote as one of several options ("remote, hybrid, or on-site") rather
# than describing an on-site role (R64-06).
_ANY_REMOTE = re.compile(r"\bremote\b|\bwork from home\b|\bwork from anywhere\b", re.I)

_NEG = re.compile(r"\b(?:not|no|isn'?t|never)\b", re.I)


# Row 64, rule type C3: phrasing that means the sentence is describing a HYBRID
# arrangement rather than a remote role. Checked inside the sentence carrying the
# remote language, which is the scope _OFFICE_CADENCE's document-wide check
# cannot express: "work from home Wednesdays" it catches, "Tuesdays and Fridays
# are remote/work from home days" it does not, because the day names arrive
# before the phrase rather than after it.
DEFAULT_HYBRID_PHRASES = (
    r"\b(?:mon|tues|wednes|thurs|fri|satur|sun)days?\b"
    r"|\bhybrid\b"
    r"|in[- ](?:the |our )?office"
    r"|on-?site"
    r"|\d+ days? (?:a |per )?week (?:in|at|on)"
    r"|in (?:the |our )?office \d+ days?"
    r"|in[- ]office \d+ days?"
    r"|(?:work|working) from home \d+ days?"
)

_SENTENCE_END = re.compile(r"[.!?\n]")


def _sentence_around(text: str, start: int, end: int) -> str:
    """The sentence a match sits in.

    Scoped to one sentence rather than to a fixed character window, because the
    unit that makes a claim about the role is the sentence. A window would cut
    "Tuesdays and Fridays are remote/work from home days" in half at any width
    narrow enough to be useful.
    """
    left = 0
    for m in _SENTENCE_END.finditer(text, 0, start):
        left = m.end()
    right_match = _SENTENCE_END.search(text, end)
    right = right_match.start() if right_match else len(text)
    return text[left:right]


def _unnegated(pattern, text, reject_in_sentence=None):
    """The first match of `pattern` that is not negated, as quoted evidence.

    Negation is checked in a 30-char window before the match ("not a remote
    position") and to the end of the sentence after it ("remote work is not
    available"). Shared by the affirmative remote override and the on-site body
    rule, which are mirror images of each other and must read a negation the
    same way — two copies of this walk would eventually disagree.

    `reject_in_sentence`, when given, also rejects a match whose own SENTENCE
    carries that pattern. A rejection continues the walk rather than ending it: a
    posting may describe a hybrid past in one sentence and a remote present in
    the next, and the later sentence is still a true statement about the role.
    """
    if not pattern:
        return None
    for m in pattern.finditer(text):
        before = text[max(0, m.start() - 30):m.start()]
        after = text[m.end():m.end() + 30].split(".")[0]
        if _NEG.search(before) or _NEG.search(after):
            continue
        if reject_in_sentence is not None and reject_in_sentence.search(
                _sentence_around(text, m.start(), m.end())):
            continue
        return evidence(m, text)
    return None


def _jd_says_remote(text, hybrid_pattern=None):
    """Affirmative remote language in the JD, skipping negated mentions.

    When `hybrid_pattern` is given, a STRONG claim about the role wins over any
    hybrid or on-site token sitting beside it, and only a WEAK mention is rejected
    for its sentence's phrasing. Without that split the tightening killed
    genuinely remote postings the untightened override had passed — "fully remote
    role with 25 days of PTO", "fully remote, with an optional desk in our
    office", "remote-first; occasional on-site offsites". Fixing miss 5 by killing
    remote roles is a worse outcome than miss 5.
    """
    strong = _unnegated(_REMOTE_STRONG, text)
    if strong:
        return strong
    return _unnegated(_REMOTE_WEAK, text, reject_in_sentence=hybrid_pattern)


def jd_says_remote(text, hybrid_pattern=None):
    """Public name for the remote-language detector above, returning the
    quoted evidence or None. engine/loop/calibrate.py contrasts remote
    language against application outcomes and needs this; reaching across
    packages for `_jd_says_remote` would make any refactor here break the
    calibrator silently, so the behavior carries a supported name instead.

    `hybrid_pattern` is opt-in rather than defaulted. The kill path passes
    `cfg.hybrid_pattern`; the calibrator does not, because tightening what a
    report says about a season already recorded is a different decision from
    tightening today's kills, and it is not this change's to make.
    """
    return _jd_says_remote(text, hybrid_pattern)


# Rule-tuning candidate 2 (Task 7): an office city stated only in the body, and
# in-office-cadence language that defeats a remote-language override.
_CITY = r"([A-Z][a-z]+(?: [A-Z][a-z]+)?(?:, [A-Z]{2})?)"
# Verb alternations are wrapped in a scoped inline (?i:...) group so "Based in
# Chicago." (sentence-initial capital) matches just like "based in Chicago"
# does. The _CITY capture sits OUTSIDE those groups on purpose — it must stay
# case-sensitive, or "we ship data based in reality" would false-positive on
# "reality" as a city.
_BODY_LOC = re.compile(r"(?i:based|located) in " + _CITY
                       + r"|(?i:office) in " + _CITY
                       + r"|(?i:on[- ]?site) in " + _CITY)
_OFFICE_CADENCE = re.compile(
    r"\d+ days? (?:a |per )?week in (?:the |our )?office|days? in[- ]office"
    r"|hybrid (?:schedule|work model|role)|in[- ]office \d+ days?"
    r"|work from home [A-Z][a-z]+days", re.I)

# The limit of "a strong claim wins" (R64-05). A posting can say "fully remote"
# and then require three days in the office; the requirement is the real term of
# the role, and letting the claim win there would hand back a hybrid job as a
# remote one. So a MANDATORY cadence — a day count tied to an office — still
# defeats the override document-wide.
#
# Narrower than _OFFICE_CADENCE on purpose: that pattern also matches "hybrid
# schedule", which appears in "Fully remote. Hybrid schedules are available for
# those who want them" — an option offered, not a term imposed.
_MANDATORY_CADENCE = re.compile(
    r"\d+ days? (?:a |per )?week (?:in|at) (?:the |our )?office"
    r"|in (?:the |our )?office \d+ days?"
    r"|in[- ]office \d+ days?"
    r"|\d+ days? in[- ]office"
    r"|\d+ days? (?:a |per )?week on-?site", re.I)


# Row 64, rule type C2: the mirror of _REMOTE_OK. Body language that describes
# the ROLE as on-site, which a header saying is_remote=True does not get to
# overrule — a posting that contradicts itself is a real class, and the
# scraper's boolean is the less reliable of the two claims.
#
# Used as the default for rules.yaml's `onsite_phrases`, so a config written
# before this rule existed still gets the fix. Setting the key REPLACES this
# set; setting it to '' turns the rule off, same shape as `commute_locations`.
DEFAULT_ONSITE_PHRASES = (
    r"fully on-?site"
    r"|100 ?% on-?site"
    r"|on-?site (?:position|role|job|opportunity)"
    r"|in[- ]office \d+ days?"
    r"|in (?:the |our )?office \d+ days?"
    r"|\d+ days? (?:a |per )?week in (?:the |our )?office"
    r"|required to (?:be|work) on-?site"
)


def body_location(text):
    m = _BODY_LOC.search(text or "")
    return next((g for g in m.groups() if g), None) if m else None


def body_stated_max(text):
    """Largest yearly salary stated in body text, or None. Conservative: a number
    only counts within 80 chars of comp-context language, and only if it lands in
    a plausible yearly band (30k-900k) — '125k events per second' must not match."""
    best = None
    for ctx in _COMP_CONTEXT.finditer(text or ""):
        window = text[max(0, ctx.start() - 80):ctx.end() + 80]
        for m in _MONEY.finditer(window):
            if not (m.group(3) or m.group(2)):      # needs 'k' or a thousands group
                continue
            val = int(m.group(1)) * 1000 if m.group(3) else int(m.group(1) + m.group(2))
            if 30_000 <= val <= 900_000:
                best = max(best or 0, val)
    return best


def _best_comp_evidence(text):
    """Same walk as body_stated_max, but also keeps the comp-context window
    that produced the best (largest) qualifying number, quoted so a human can
    overrule a bad parse. Returns (best_value, quoted_snippet) or (None, None)."""
    best = None
    best_window = None
    for ctx in _COMP_CONTEXT.finditer(text or ""):
        window = text[max(0, ctx.start() - 80):ctx.end() + 80]
        for m in _MONEY.finditer(window):
            if not (m.group(3) or m.group(2)):
                continue
            val = int(m.group(1)) * 1000 if m.group(3) else int(m.group(1) + m.group(2))
            if 30_000 <= val <= 900_000 and (best is None or val > best):
                best = val
                best_window = window
    if best is None:
        return None, None
    return best, best_window.replace("\n", " ").strip()


def evidence(match, text: str) -> str:
    """±40-char context window around a regex match, newlines flattened to
    spaces, so a kill flag can be reviewed without opening the full JD."""
    start = max(0, match.start() - 40)
    end = match.end() + 40
    return text[start:end].replace("\n", " ").strip()


def _onsite_says(text, pattern):
    """On-site language describing THIS role, or None.

    Two rejections, not one. A negated mention ("this is not an on-site role") is
    skipped by the shared negation window, as everywhere else. And a match whose
    own sentence carries an unnegated mention of remote work is skipped too,
    because a posting that says "remote, hybrid, or on-site positions" is
    describing a CHOICE rather than an on-site role — and the choice includes what
    the reader wants (R64-06).

    A DENIED remote mention does not rescue it: "this role is not remote; it is a
    fully on-site position" is a statement of the terms, not an option, which is
    why the sentence check goes through `_unnegated` rather than a bare search.
    """
    if not pattern:
        return None
    for m in pattern.finditer(text):
        before = text[max(0, m.start() - 30):m.start()]
        after = text[m.end():m.end() + 30].split(".")[0]
        if _NEG.search(before) or _NEG.search(after):
            continue
        sentence = _sentence_around(text, m.start(), m.end())
        if _unnegated(_ANY_REMOTE, sentence):
            continue
        return evidence(m, text)
    return None


def title_passes(title: Optional[str], cfg) -> bool:
    t = title or ""
    return bool(cfg.title_keep.search(t)) and not cfg.title_drop.search(t)


def kill_flags(row: dict, cfg) -> list:
    """Run every kill check against a row, in order, and return the flags
    that fired as (rule_name, evidence) pairs. Config regex rules run first;
    comp rules (Task 6) and the location rule (Task 7) extend this same list
    after the regex-rule loop below."""
    flags = []
    text = str(row.get("description") or "")

    for rule in cfg.kill_rules:
        match = rule.pattern.search(text)
        if match:
            flags.append((rule.name, evidence(match, text)))

    max_amount = row.get("max_amount")
    if max_amount:
        interval = str(row.get("interval") or "yearly").lower()
        if interval == "yearly" and float(max_amount) < cfg.comp_floor:
            flags.append(("comp-below-floor", f"posted max ${int(float(max_amount)):,}"))
    else:
        stated_max, snippet = _best_comp_evidence(text)
        if stated_max is not None and stated_max < cfg.comp_floor:
            flags.append(("comp-below-floor-stated", snippet))

    # Where the posting says it is, computed ONCE and outside the is_remote
    # guard below, because the on-site body rule needs it too — and that rule
    # has to run even when the header claims the role is remote.
    structured_location = str(row.get("location") or "").strip()
    body_match = None if structured_location else _BODY_LOC.search(text)
    effective_location = structured_location or (
        next((g for g in body_match.groups() if g), None) if body_match else None
    )
    # Normalised, word-bounded matching — never a bare substring of the raw
    # string. See engine/radar/location.py: a `NY` allowlist used to match
    # "Pennsylvania, United States" and miss "New York, United States", so one
    # place got two verdicts in one run.
    commute_matches = pattern_matches_location(cfg.commute_pattern, effective_location)

    # The body contradicting its own header. The commute allowlist WINS over
    # this: an on-site role in a city the user can actually commute to is a role
    # they want, and killing it would be the opposite of the miss being fixed.
    if not commute_matches:
        onsite_evidence = _onsite_says(text, cfg.onsite_pattern)
        if onsite_evidence:
            flags.append(("onsite-body", onsite_evidence))

    if not row.get("is_remote"):
        if effective_location:
            if not commute_matches:
                override = (_jd_says_remote(text, cfg.hybrid_pattern)
                            and not _MANDATORY_CADENCE.search(text))
                if not override:
                    loc_evidence = structured_location if structured_location else evidence(body_match, text)
                    flags.append(("location", loc_evidence))
        else:
            cadence_match = _OFFICE_CADENCE.search(text)
            if cadence_match:
                commute_matches_anywhere = bool(cfg.commute_pattern and cfg.commute_pattern.search(text))
                if not commute_matches_anywhere:
                    flags.append(("location", evidence(cadence_match, text)))

    return flags


# Row 64, rule type C4: the years-of-experience band, read at BOTH ends.
#
# A band is a weak claim about a req — boards and recruiters mislabel seniority
# constantly — and the miss was a ranking failure, not a visibility one. So the
# floor costs points and the stretch costs nothing, and neither one ever kills.
_YEARS = r"(?:years?|yrs?)"
# Alternations ordered most specific first, so "1-4 years" is read as a band
# rather than as the bare "4 years" the last alternation would find.
_BAND = re.compile("|".join((
    r"(\d{1,2})\s*(?:-|–|—|to)\s*\d{1,2}\+?\s*" + _YEARS,
    r"(?:at least|minimum of|min\.? of)\s*(\d{1,2})\+?\s*" + _YEARS,
    r"(\d{1,2})\+\s*" + _YEARS,
    r"(\d{1,2})\s*" + _YEARS,
)), re.I)

# Phrase floors — a posting that says "early in their career" has stated a floor
# without stating a number, and treating it as 0 is what the words mean.
_PHRASE_FLOOR = re.compile(
    r"early in (?:their|your|his or her) career"
    r"|entry[- ]level"
    r"|new grad(?:uate)?s?"
    r"|recent grad(?:uate)?s?", re.I)


def experience_signals(text) -> list:
    """Every stated experience floor in a body, as (low_years, match) pairs.

    The LOW end of each band is what a floor check needs — "1-4 years" is a
    junior req whatever its upper bound is. A phrase floor ("entry level")
    contributes a low of 0, because that is what the phrase means.
    """
    body = str(text or "")
    signals = []
    for m in _BAND.finditer(body):
        low = next((g for g in m.groups() if g), None)
        if low is not None:
            signals.append((int(low), m))
    for m in _PHRASE_FLOOR.finditer(body):
        signals.append((0, m))
    return signals


def seniority_notes(row: dict, cfg) -> list:
    """Non-kill (name, evidence) notes about the posting's stated seniority.

    Separate from `kill_flags` because these are not kills and must never be
    mistaken for them by a caller iterating flags. Empty when no `seniority`
    block is configured: a floor is a personal preference like the comp floor,
    and there is no honest default to invent for someone who never stated one.
    """
    seniority = getattr(cfg, "seniority", None)
    if not seniority:
        return []

    text = str(row.get("description") or "")
    signals = experience_signals(text)
    if not signals:
        return []

    notes = []
    lowest, lowest_match = min(signals, key=lambda s: s[0])
    if lowest < seniority["min_years"]:
        notes.append(("junior-band", evidence(lowest_match, text)))

    highest, highest_match = max(signals, key=lambda s: s[0])
    if highest >= seniority["stretch_years"]:
        notes.append(("seniority-stretch", evidence(highest_match, text)))
    return notes


def seniority_penalty(row: dict, cfg) -> int:
    """The points a junior band costs this row. Zero when nothing is flagged."""
    seniority = getattr(cfg, "seniority", None)
    if not seniority:
        return 0
    if any(name == "junior-band" for name, _ in seniority_notes(row, cfg)):
        return seniority["penalty"]
    return 0


def _days_old(date_posted, today: "datetime.date") -> int:
    """Port of OLD/rules.py::_days_old (lines 107-141). A missing date_posted
    can't be aged at all, so it's treated as a fixed 14 days old (stale enough
    to fall into the old_pts bucket without pretending we know the real age).
    A string is parsed as an ISO date (only the first 10 chars, so a full
    ISO timestamp still works); a datetime is narrowed to its date. Negative
    ages (a future date_posted, e.g. clock skew) are clamped to 0."""
    if date_posted is None:
        return 14
    if isinstance(date_posted, str):
        date_posted = datetime.date.fromisoformat(date_posted[:10])
    elif isinstance(date_posted, datetime.datetime):
        date_posted = date_posted.date()
    return max(0, (today - date_posted).days)


def score(row: dict, today: "datetime.date", cfg) -> int:
    """Port of OLD/rules.py::score (lines 107-141), generic over cfg.title_tiers
    and cfg.weights. Higher score means a posting is more worth a human's
    attention: a matching senior title, comp that clears the target or floor,
    freshness, remote-friendliness, and seniority language in the title all
    add points; everything else falls back to config defaults."""
    title = str(row.get("title") or "")

    pts = cfg.weights["default_title_pts"]
    for pattern, tier_pts in cfg.title_tiers:
        if pattern.search(title):
            pts = tier_pts
            break

    max_amount = row.get("max_amount")
    if max_amount and float(max_amount) >= cfg.weights["comp_target"]:
        pts += cfg.weights["target_comp_pts"]
    elif max_amount and float(max_amount) >= cfg.comp_floor:
        pts += cfg.weights["floor_comp_pts"]
    elif not max_amount:
        pts += cfg.weights["unlisted_comp_pts"]

    age = _days_old(row.get("date_posted"), today)
    if age <= cfg.weights["fresh_days"]:
        pts += cfg.weights["fresh_pts"]
    elif age <= 7:
        pts += cfg.weights["week_pts"]
    else:
        pts += cfg.weights["old_pts"]

    if row.get("is_remote"):
        pts += cfg.weights["remote_pts"]

    if cfg.weights["seniority_pattern"].search(title):
        pts += cfg.weights["seniority_pts"]

    # A stated floor below the configured one costs points rather than killing.
    # Deliberately NOT clamped at zero: two junior reqs that differ in every
    # other dimension should still rank against each other, and clamping throws
    # that ordering away to make a number look tidier.
    pts -= seniority_penalty(row, cfg)

    return pts


_CLOSED_PHRASE = re.compile(r"no longer accepting applications", re.I)


def posting_status(http_status, body) -> str:
    """Port of OLD/rules.py (lines 149-166), fully generic — classifies whether
    a job posting is still live by re-fetching its URL. "unknown" is NOT a soft
    "dead" — a rate limit or server error means we learned nothing; only an
    explicit 404/410 or a page saying it stopped accepting applications counts
    as dead. Treating "unknown" as "dead" would silently kill postings on
    nothing more than a transient network hiccup."""
    if http_status in (404, 410):
        return "dead"
    if http_status == 200:
        normalized = re.sub(r"\s+", " ", body or "")
        return "dead" if _CLOSED_PHRASE.search(normalized) else "live"
    return "unknown"
