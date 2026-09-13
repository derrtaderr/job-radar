"""Rules engine — title filter and kill-flag evaluation. Config-driven: the
engine has no opinions of its own, it just runs the judgment that lives in
Config (title_keep/title_drop, kill_rules, and — from Tasks 6/7 — comp_floor
and commute_pattern) against a JobSpy-shaped row.
"""
from __future__ import annotations

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
