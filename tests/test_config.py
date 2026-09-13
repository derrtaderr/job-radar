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
