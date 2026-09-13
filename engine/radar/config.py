"""Config loader — reads the judgment layer (config/ or config.example/) into a
typed Config object. The engine has no opinions of its own; everything a person's
search cares about (queries, kill rules, weights, output paths) lives in the five
files this module reads, and nothing here ever writes personal data back out.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

REQUIRED_FILES = ("queries.yaml", "rules.yaml", "weights.yaml", "settings.yaml", "exclusions.txt")


class ConfigError(Exception):
    """Raised for anything wrong with a config directory: missing, malformed, or
    carrying a regex that won't compile. Always names the offending file/key/rule
    so fixing it is a one-line lookup, not an archaeology project."""


@dataclass
class KillRule:
    name: str
    reason: str
    pattern: "re.Pattern[str]"


@dataclass
class Config:
    queries: list
    sites: list
    search_location: str
    hours_old: int
    results_per_query: int
    title_keep: "re.Pattern[str]"
    title_drop: "re.Pattern[str]"
    kill_rules: list
    comp_floor: int
    commute_pattern: "Optional[re.Pattern[str]]"
    title_tiers: list
    weights: dict
    output_dir: Path
    state_file: Path
    tracker_path: "Optional[Path]"
    tracker_active_sections: set
    closed_window_days: int
    exclusions: list


def _require(data: dict, key: str, filename: str):
    value = data.get(key)
    if value is None:
        raise ConfigError(f"missing required key {key!r} in {filename}")
    return value


def _require_int(data: dict, key: str, where: str) -> int:
    # PyYAML parses `yes`/`no`/`true`/`false` as bool, and bool is a subclass of
    # int in Python (True == 1), so `isinstance(x, int)` alone lets a typo'd
    # `points: yes` through as a silent 1. A float (`15.0`) passes the "it's a
    # number" instinct too but violates the int contract just as quietly.
    # Both must be rejected explicitly, not just "isn't missing."
    value = _require(data, key, where)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigError(f"{key!r} in {where} must be an integer, got {value!r}")
    return value


def _compile(pattern: str, where: str) -> "re.Pattern[str]":
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise ConfigError(f"bad regex in {where}: {pattern!r} — {exc}") from exc


def _load_yaml(path: Path, filename: str) -> dict:
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ConfigError(f"bad yaml in {filename}: {exc}") from exc
    return data or {}


def _load_exclusions(path: Path) -> list:
    # Port of OLD/radar.py::load_exclusions — strip, drop blanks and # comments,
    # lowercase for case-insensitive substring matching downstream.
    exclusions = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        exclusions.append(line.lower())
    return exclusions


def load_config(config_dir: Path) -> Config:
    config_dir = Path(config_dir)
    if not config_dir.is_dir() or not all((config_dir / f).exists() for f in REQUIRED_FILES):
        raise ConfigError(
            f"no config at {config_dir} — copy config.example/ to config/ and edit it "
            "(see config.example/README.md)"
        )

    queries_raw = _load_yaml(config_dir / "queries.yaml", "queries.yaml")
    rules_raw = _load_yaml(config_dir / "rules.yaml", "rules.yaml")
    weights_raw = _load_yaml(config_dir / "weights.yaml", "weights.yaml")
    settings_raw = _load_yaml(config_dir / "settings.yaml", "settings.yaml")

    # --- queries.yaml ---
    queries = _require(queries_raw, "searches", "queries.yaml")
    sites = _require(queries_raw, "sites", "queries.yaml")
    search_location = _require(queries_raw, "location", "queries.yaml")
    hours_old = _require_int(queries_raw, "hours_old", "queries.yaml")
    results_per_query = _require_int(queries_raw, "results_per_query", "queries.yaml")
    title_keep = _compile(_require(queries_raw, "title_keep", "queries.yaml"), "queries.yaml title_keep")
    title_drop = _compile(_require(queries_raw, "title_drop", "queries.yaml"), "queries.yaml title_drop")

    # --- rules.yaml ---
    comp_floor = _require_int(rules_raw, "comp_floor", "rules.yaml")
    commute_locations = rules_raw.get("commute_locations") or None
    commute_pattern = (
        _compile(commute_locations, "rules.yaml commute_locations") if commute_locations else None
    )

    kill_rules = []
    for idx, rule in enumerate(rules_raw.get("rules") or []):
        name = _require(rule, "name", f"rules.yaml rule #{idx}")
        reason = _require(rule, "reason", f"rules.yaml rule {name!r}")
        pattern_raw = _require(rule, "pattern", f"rules.yaml rule {name!r}")
        pattern = _compile(pattern_raw, f"rules.yaml rule {name!r}")
        kill_rules.append(KillRule(name=name, reason=reason, pattern=pattern))

    # --- weights.yaml ---
    title_tiers = []
    for idx, tier in enumerate(weights_raw.get("title_tiers") or []):
        pattern_raw = _require(tier, "pattern", f"weights.yaml title_tiers #{idx}")
        points = _require_int(tier, "points", f"weights.yaml title_tiers {pattern_raw!r}")
        pattern = _compile(pattern_raw, f"weights.yaml title_tiers {pattern_raw!r}")
        title_tiers.append((pattern, points))

    seniority_pattern_raw = _require(weights_raw, "seniority_pattern", "weights.yaml")
    weights = {
        "comp_target": _require_int(weights_raw, "comp_target", "weights.yaml"),
        "target_comp_pts": _require_int(weights_raw, "target_comp_pts", "weights.yaml"),
        "floor_comp_pts": _require_int(weights_raw, "floor_comp_pts", "weights.yaml"),
        "unlisted_comp_pts": _require_int(weights_raw, "unlisted_comp_pts", "weights.yaml"),
        "fresh_days": _require_int(weights_raw, "fresh_days", "weights.yaml"),
        "fresh_pts": _require_int(weights_raw, "fresh_pts", "weights.yaml"),
        "week_pts": _require_int(weights_raw, "week_pts", "weights.yaml"),
        "old_pts": _require_int(weights_raw, "old_pts", "weights.yaml"),
        "remote_pts": _require_int(weights_raw, "remote_pts", "weights.yaml"),
        "seniority_pattern": _compile(seniority_pattern_raw, "weights.yaml seniority_pattern"),
        "seniority_pts": _require_int(weights_raw, "seniority_pts", "weights.yaml"),
        "default_title_pts": _require_int(weights_raw, "default_title_pts", "weights.yaml"),
    }

    # --- settings.yaml ---
    base = config_dir.parent
    output_dir = (base / _require(settings_raw, "output_dir", "settings.yaml")).resolve()
    state_file = (base / _require(settings_raw, "state_file", "settings.yaml")).resolve()
    tracker = settings_raw.get("tracker") or None
    tracker_path = (base / tracker).resolve() if tracker else None
    tracker_active_sections = set(_require(settings_raw, "tracker_active_sections", "settings.yaml"))
    closed_window_days = _require_int(settings_raw, "closed_window_days", "settings.yaml")

    # --- exclusions.txt ---
    exclusions = _load_exclusions(config_dir / "exclusions.txt")

    return Config(
        queries=queries,
        sites=sites,
        search_location=search_location,
        hours_old=hours_old,
        results_per_query=results_per_query,
        title_keep=title_keep,
        title_drop=title_drop,
        kill_rules=kill_rules,
        comp_floor=comp_floor,
        commute_pattern=commute_pattern,
        title_tiers=title_tiers,
        weights=weights,
        output_dir=output_dir,
        state_file=state_file,
        tracker_path=tracker_path,
        tracker_active_sections=tracker_active_sections,
        closed_window_days=closed_window_days,
        exclusions=exclusions,
    )
