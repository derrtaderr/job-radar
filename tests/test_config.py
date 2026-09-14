import pytest
from pathlib import Path

from engine.radar.config import load_config, ConfigError

EXAMPLE = Path(__file__).parent.parent / "config.example"


def test_example_config_loads():
    cfg = load_config(EXAMPLE)
    assert cfg.queries and cfg.comp_floor > 0
    assert cfg.title_keep.search("Data Engineer")
    assert any(r.name == "bdr-scope" for r in cfg.kill_rules)


def test_missing_dir_names_the_fix(tmp_path):
    with pytest.raises(ConfigError, match="copy config.example"):
        load_config(tmp_path / "nope")


def test_bad_regex_names_the_rule(tmp_path):
    (tmp_path / "rules.yaml").write_text("comp_floor: 1\nrules:\n  - {name: broken, reason: x, pattern: '('}\n")
    for f in ("queries", "weights", "settings"):
        (tmp_path / f"{f}.yaml").write_text((EXAMPLE / f"{f}.yaml").read_text())
    (tmp_path / "exclusions.txt").write_text("")
    with pytest.raises(ConfigError, match="broken"):
        load_config(tmp_path)


def test_rule_missing_reason_names_the_rule(tmp_path):
    (tmp_path / "rules.yaml").write_text(
        "comp_floor: 1\nrules:\n  - {name: incomplete, pattern: 'x'}\n"
    )
    for f in ("queries", "weights", "settings"):
        (tmp_path / f"{f}.yaml").write_text((EXAMPLE / f"{f}.yaml").read_text())
    (tmp_path / "exclusions.txt").write_text("")
    with pytest.raises(ConfigError, match="incomplete"):
        load_config(tmp_path)


def test_tier_missing_points_names_the_tier(tmp_path):
    broken_weights = (EXAMPLE / "weights.yaml").read_text().replace(
        "  - {pattern: 'analytics engineer', points: 15}",
        "  - {pattern: 'analytics engineer'}",
    )
    (tmp_path / "weights.yaml").write_text(broken_weights)
    for f in ("queries", "rules", "settings"):
        (tmp_path / f"{f}.yaml").write_text((EXAMPLE / f"{f}.yaml").read_text())
    (tmp_path / "exclusions.txt").write_text("")
    with pytest.raises(ConfigError, match="analytics engineer"):
        load_config(tmp_path)


def test_tier_points_bool_rejected(tmp_path):
    # PyYAML parses `yes` as True, and True == 1 in Python — a 30-point tier
    # written as `points: yes` would silently score as 1 instead of failing loudly.
    broken_weights = (EXAMPLE / "weights.yaml").read_text().replace(
        "  - {pattern: 'analytics engineer', points: 15}",
        "  - {pattern: 'analytics engineer', points: yes}",
    )
    (tmp_path / "weights.yaml").write_text(broken_weights)
    for f in ("queries", "rules", "settings"):
        (tmp_path / f"{f}.yaml").write_text((EXAMPLE / f"{f}.yaml").read_text())
    (tmp_path / "exclusions.txt").write_text("")
    with pytest.raises(ConfigError, match="analytics engineer"):
        load_config(tmp_path)


def test_tier_points_float_rejected(tmp_path):
    broken_weights = (EXAMPLE / "weights.yaml").read_text().replace(
        "  - {pattern: 'analytics engineer', points: 15}",
        "  - {pattern: 'analytics engineer', points: 15.0}",
    )
    (tmp_path / "weights.yaml").write_text(broken_weights)
    for f in ("queries", "rules", "settings"):
        (tmp_path / f"{f}.yaml").write_text((EXAMPLE / f"{f}.yaml").read_text())
    (tmp_path / "exclusions.txt").write_text("")
    with pytest.raises(ConfigError, match="analytics engineer"):
        load_config(tmp_path)


def test_scalar_searches_rejected(tmp_path):
    # A typo'd `searches: Data Engineer` loads as a plain str, and scrape()
    # would silently run one query per character instead of one per title.
    broken_queries = (EXAMPLE / "queries.yaml").read_text().replace(
        'searches:\n  - "Data Engineer"\n  - "Analytics Engineer"\n  - "Data Platform Engineer"',
        "searches: Data Engineer",
    )
    (tmp_path / "queries.yaml").write_text(broken_queries)
    for f in ("rules", "weights", "settings"):
        (tmp_path / f"{f}.yaml").write_text((EXAMPLE / f"{f}.yaml").read_text())
    (tmp_path / "exclusions.txt").write_text("")
    with pytest.raises(ConfigError, match="searches"):
        load_config(tmp_path)


def test_scalar_sites_rejected(tmp_path):
    broken_queries = (EXAMPLE / "queries.yaml").read_text().replace(
        "sites: [linkedin]", "sites: linkedin"
    )
    (tmp_path / "queries.yaml").write_text(broken_queries)
    for f in ("rules", "weights", "settings"):
        (tmp_path / f"{f}.yaml").write_text((EXAMPLE / f"{f}.yaml").read_text())
    (tmp_path / "exclusions.txt").write_text("")
    with pytest.raises(ConfigError, match="sites"):
        load_config(tmp_path)


def test_empty_searches_rejected(tmp_path):
    broken_queries = (EXAMPLE / "queries.yaml").read_text().replace(
        'searches:\n  - "Data Engineer"\n  - "Analytics Engineer"\n  - "Data Platform Engineer"',
        "searches: []",
    )
    (tmp_path / "queries.yaml").write_text(broken_queries)
    for f in ("rules", "weights", "settings"):
        (tmp_path / f"{f}.yaml").write_text((EXAMPLE / f"{f}.yaml").read_text())
    (tmp_path / "exclusions.txt").write_text("")
    with pytest.raises(ConfigError, match="searches"):
        load_config(tmp_path)


def test_scalar_tracker_active_sections_rejected(tmp_path):
    broken_settings = (EXAMPLE / "settings.yaml").read_text().replace(
        "tracker_active_sections: [active, drafted but not applied]",
        "tracker_active_sections: active",
    )
    (tmp_path / "settings.yaml").write_text(broken_settings)
    for f in ("queries", "rules", "weights"):
        (tmp_path / f"{f}.yaml").write_text((EXAMPLE / f"{f}.yaml").read_text())
    (tmp_path / "exclusions.txt").write_text("")
    with pytest.raises(ConfigError, match="tracker_active_sections"):
        load_config(tmp_path)


def test_comp_floor_bool_rejected(tmp_path):
    # Same silent-misbehavior class as the tier `points` bug, extended to
    # comp_floor since it's compared numerically downstream the same way.
    broken_rules = (EXAMPLE / "rules.yaml").read_text().replace(
        "comp_floor: 120000", "comp_floor: yes"
    )
    (tmp_path / "rules.yaml").write_text(broken_rules)
    for f in ("queries", "weights", "settings"):
        (tmp_path / f"{f}.yaml").write_text((EXAMPLE / f"{f}.yaml").read_text())
    (tmp_path / "exclusions.txt").write_text("")
    with pytest.raises(ConfigError, match="comp_floor"):
        load_config(tmp_path)


# --- followup_after_days: optional strict-int key, defaults to 10 ---------
# Same optional-key shape as `tracker: null` (settings.yaml may omit it
# entirely) plus the same int-not-bool guard as comp_floor/points (a
# `followup_after_days: yes` typo must not silently become 1).

def _settings_without_followup_key(base_text: str) -> str:
    lines = [l for l in base_text.splitlines() if not l.strip().startswith("followup_after_days")]
    return "\n".join(lines) + "\n"


def test_example_config_has_followup_after_days_10():
    cfg = load_config(EXAMPLE)
    assert cfg.followup_after_days == 10


def test_followup_after_days_defaults_to_10_when_absent(tmp_path):
    settings = _settings_without_followup_key((EXAMPLE / "settings.yaml").read_text())
    (tmp_path / "settings.yaml").write_text(settings)
    for f in ("queries", "rules", "weights"):
        (tmp_path / f"{f}.yaml").write_text((EXAMPLE / f"{f}.yaml").read_text())
    (tmp_path / "exclusions.txt").write_text("")
    cfg = load_config(tmp_path)
    assert cfg.followup_after_days == 10


def test_followup_after_days_custom_value_respected(tmp_path):
    settings = _settings_without_followup_key((EXAMPLE / "settings.yaml").read_text())
    settings += "followup_after_days: 5\n"
    (tmp_path / "settings.yaml").write_text(settings)
    for f in ("queries", "rules", "weights"):
        (tmp_path / f"{f}.yaml").write_text((EXAMPLE / f"{f}.yaml").read_text())
    (tmp_path / "exclusions.txt").write_text("")
    cfg = load_config(tmp_path)
    assert cfg.followup_after_days == 5


def test_followup_after_days_bool_rejected(tmp_path):
    settings = _settings_without_followup_key((EXAMPLE / "settings.yaml").read_text())
    settings += "followup_after_days: yes\n"
    (tmp_path / "settings.yaml").write_text(settings)
    for f in ("queries", "rules", "weights"):
        (tmp_path / f"{f}.yaml").write_text((EXAMPLE / f"{f}.yaml").read_text())
    (tmp_path / "exclusions.txt").write_text("")
    with pytest.raises(ConfigError, match="followup_after_days"):
        load_config(tmp_path)


def test_followup_after_days_float_rejected(tmp_path):
    settings = _settings_without_followup_key((EXAMPLE / "settings.yaml").read_text())
    settings += "followup_after_days: 7.5\n"
    (tmp_path / "settings.yaml").write_text(settings)
    for f in ("queries", "rules", "weights"):
        (tmp_path / f"{f}.yaml").write_text((EXAMPLE / f"{f}.yaml").read_text())
    (tmp_path / "exclusions.txt").write_text("")
    with pytest.raises(ConfigError, match="followup_after_days"):
        load_config(tmp_path)


# --- archive_dir: optional path key, defaults to ./archive -----------------
# Same optional-key shape as `tracker: null` / followup_after_days (settings.yaml
# may omit it entirely), resolved relative to config_dir.parent exactly like
# output_dir/state_file/tracker.

def _settings_without_archive_key(base_text: str) -> str:
    lines = [l for l in base_text.splitlines() if not l.strip().startswith("archive_dir")]
    return "\n".join(lines) + "\n"


def test_archive_dir_defaults_to_archive_when_absent(tmp_path):
    settings = _settings_without_archive_key((EXAMPLE / "settings.yaml").read_text())
    (tmp_path / "settings.yaml").write_text(settings)
    for f in ("queries", "rules", "weights"):
        (tmp_path / f"{f}.yaml").write_text((EXAMPLE / f"{f}.yaml").read_text())
    (tmp_path / "exclusions.txt").write_text("")
    cfg = load_config(tmp_path)
    assert cfg.archive_dir == (tmp_path.parent / "archive").resolve()


def test_archive_dir_custom_value_respected(tmp_path):
    settings = _settings_without_archive_key((EXAMPLE / "settings.yaml").read_text())
    settings += "archive_dir: ./my-archive\n"
    (tmp_path / "settings.yaml").write_text(settings)
    for f in ("queries", "rules", "weights"):
        (tmp_path / f"{f}.yaml").write_text((EXAMPLE / f"{f}.yaml").read_text())
    (tmp_path / "exclusions.txt").write_text("")
    cfg = load_config(tmp_path)
    assert cfg.archive_dir == (tmp_path.parent / "my-archive").resolve()


def test_archive_dir_non_string_rejected(tmp_path):
    settings = _settings_without_archive_key((EXAMPLE / "settings.yaml").read_text())
    settings += "archive_dir: yes\n"
    (tmp_path / "settings.yaml").write_text(settings)
    for f in ("queries", "rules", "weights"):
        (tmp_path / f"{f}.yaml").write_text((EXAMPLE / f"{f}.yaml").read_text())
    (tmp_path / "exclusions.txt").write_text("")
    with pytest.raises(ConfigError, match="archive_dir"):
        load_config(tmp_path)


# --- archive_dir: '' means absent, same as tracker: '' ----------------------

def test_empty_archive_dir_falls_back_to_the_default(tmp_path):
    # `tracker: ''` already resolves to "no tracker" via `or None`. An empty
    # archive_dir went the other way: it is a str, so it passed the type
    # guard and resolved to the CONFIG'S PARENT directory — making the whole
    # repo root the archive, where every sibling folder reads as an archived
    # application.
    from engine.radar.config import load_config
    cfg_dir = _copy_example(tmp_path)
    settings = (cfg_dir / "settings.yaml")
    settings.write_text(settings.read_text() + "\narchive_dir: ''\n")

    cfg = load_config(cfg_dir)

    assert cfg.archive_dir == (cfg_dir.parent / "archive").resolve()


def test_whitespace_only_archive_dir_also_falls_back(tmp_path):
    from engine.radar.config import load_config
    cfg_dir = _copy_example(tmp_path)
    settings = (cfg_dir / "settings.yaml")
    settings.write_text(settings.read_text() + "\narchive_dir: '   '\n")

    cfg = load_config(cfg_dir)

    assert cfg.archive_dir == (cfg_dir.parent / "archive").resolve()


def test_a_real_archive_dir_is_still_honored(tmp_path):
    from engine.radar.config import load_config
    cfg_dir = _copy_example(tmp_path)
    settings = (cfg_dir / "settings.yaml")
    settings.write_text(settings.read_text() + "\narchive_dir: ./filed\n")

    cfg = load_config(cfg_dir)

    assert cfg.archive_dir == (cfg_dir.parent / "filed").resolve()


def _copy_example(tmp_path):
    """A writable copy of config.example under tmp_path/config."""
    import shutil
    cfg_dir = tmp_path / "config"
    shutil.copytree(EXAMPLE, cfg_dir)
    return cfg_dir
