"""Rules engine — title filter and kill-flag evaluation. Config-driven: the
engine has no opinions of its own, it just runs the judgment that lives in
Config (title_keep/title_drop, kill_rules, and — from Tasks 6/7 — comp_floor
and commute_pattern) against a JobSpy-shaped row.
"""
from __future__ import annotations

import datetime
import re
from typing import Optional

_COMP_CONTEXT = re.compile(r"salary|compensation|base pay|pay range|\bcomp\b|\bOTE\b", re.I)
_MONEY = re.compile(r"\$?\s?(\d{2,3})(?:,(\d{3}))?\s?(k\b)?", re.I)

# Ported verbatim from OLD/rules.py (lines 55-78) — generic engine constants for
# detecting affirmative remote language in a JD while skipping negated mentions.
_REMOTE_OK = re.compile(
    r"fully remote|100 ?% remote|remote[- ]first|remote[- ]friendly|remote[- ]eligible"
    r"|remote (?:position|role|opportunity|job)"
    r"|work from home|work from anywhere|work(?:ing)? remotely"
    r"|#li[- ]remote"
    r"|remote \((?:us|usa|united states|anywhere)"
    r"|(?:us|u\.s\.|usa)[- ]remote"
    r"|remote,? (?:us\b|usa\b|united states)"
    r"|open to remote", re.I)

_NEG = re.compile(r"\b(?:not|no|isn'?t|never)\b", re.I)


def _jd_says_remote(text):
    """Affirmative remote language in the JD, skipping negated mentions — "not a
    remote position" (negation before) and "remote work is not available"
    (negation after, checked only to the end of the sentence)."""
    for m in _REMOTE_OK.finditer(text):
        before = text[max(0, m.start() - 30):m.start()]
        after = text[m.end():m.end() + 30].split(".")[0]
        if _NEG.search(before) or _NEG.search(after):
            continue
        return evidence(m, text)
    return None


# Rule-tuning candidate 2 (Task 7): an office city stated only in the body, and
# in-office-cadence language that defeats a remote-language override.
_CITY = r"([A-Z][a-z]+(?: [A-Z][a-z]+)?(?:, [A-Z]{2})?)"
_BODY_LOC = re.compile(r"(?:based|located) in " + _CITY
                       + r"|office in " + _CITY
                       + r"|on[- ]?site in " + _CITY)
_OFFICE_CADENCE = re.compile(
    r"\d+ days? (?:a |per )?week in (?:the |our )?office|days? in[- ]office"
    r"|hybrid (?:schedule|work model|role)|in[- ]office \d+ days?"
    r"|work from home [A-Z][a-z]+days", re.I)


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

    if not row.get("is_remote"):
        structured_location = str(row.get("location") or "").strip()
        body_match = None if structured_location else _BODY_LOC.search(text)
        effective_location = structured_location or (
            next((g for g in body_match.groups() if g), None) if body_match else None
        )

        if effective_location:
            commute_matches = bool(cfg.commute_pattern and cfg.commute_pattern.search(effective_location))
            if not commute_matches:
                override = _jd_says_remote(text) and not _OFFICE_CADENCE.search(text)
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
