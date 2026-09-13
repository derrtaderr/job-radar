"""Rules engine — title filter and kill-flag evaluation. Config-driven: the
engine has no opinions of its own, it just runs the judgment that lives in
Config (title_keep/title_drop, kill_rules, and — from Tasks 6/7 — comp_floor
and commute_pattern) against a JobSpy-shaped row.
"""
from __future__ import annotations

from typing import Optional


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

    return flags
