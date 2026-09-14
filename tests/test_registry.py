"""Template registry — the lookup layer /apply (Task 9) uses to resolve a
template name to its source path, kind, and page limit. Same loud-failure
standard as the config loader: a malformed or missing entry raises
RegistryError naming the offending entry, never a silent default.
"""
from pathlib import Path

import pytest

from engine.draft.registry import RegistryError, load_registry

REPO_ROOT = Path(__file__).parent.parent


def test_stock_registry_loads():
    registry = load_registry(REPO_ROOT)

    resume = registry.get("stock-resume")
    assert resume.name == "stock-resume"
    assert resume.source == REPO_ROOT / "templates" / "resume.typ"
    assert resume.kind == "resume"
    assert resume.page_limit == 2

    cover = registry.get("stock-cover")
    assert cover.kind == "cover"
    assert cover.page_limit == 1


def test_default_resolves_by_kind():
    # Deliberately does NOT pin the literal stock names. /add-template lets a
    # user point default_resume at their own template, whose source lives in
    # gitignored templates/custom/ — a legitimate local state that must not
    # fail the suite. What the default contract actually promises is that each
    # kind resolves to a registered template OF THAT KIND with a usable page
    # budget, and that is what this asserts. test_stock_registry_loads still
    # pins the stock entries themselves by name.
    registry = load_registry(REPO_ROOT)

    for kind in ("resume", "cover"):
        default = registry.default(kind)
        assert default.name in registry.templates
        assert registry.get(default.name) is default
        assert default.kind == kind
        assert default.page_limit >= 1


def test_unknown_default_kind_names_known_kinds():
    registry = load_registry(REPO_ROOT)

    with pytest.raises(RegistryError, match="resume"):
        registry.default("nope")


def test_unknown_get_name_names_known_names(tmp_path):
    registry = load_registry(REPO_ROOT)

    with pytest.raises(RegistryError, match="stock-resume") as exc_info:
        registry.get("does-not-exist")
    assert "stock-cover" in str(exc_info.value)


def test_missing_page_limit_names_the_entry(tmp_path):
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "resume.typ").write_text("")
    (tmp_path / "templates.yaml").write_text("")
    (tmp_path / "templates" / "registry.yaml").write_text(
        "default_resume: broken\n"
        "default_cover: broken\n"
        "templates:\n"
        "  - {name: broken, source: templates/resume.typ, kind: resume}\n"
    )

    with pytest.raises(RegistryError, match="broken"):
        load_registry(tmp_path)


def test_page_limit_bool_rejected(tmp_path):
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "resume.typ").write_text("")
    (tmp_path / "templates" / "registry.yaml").write_text(
        "default_resume: broken\n"
        "default_cover: broken\n"
        "templates:\n"
        "  - {name: broken, source: templates/resume.typ, kind: resume, page_limit: yes}\n"
    )

    with pytest.raises(RegistryError, match="broken"):
        load_registry(tmp_path)


def test_page_limit_float_rejected(tmp_path):
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "resume.typ").write_text("")
    (tmp_path / "templates" / "registry.yaml").write_text(
        "default_resume: broken\n"
        "default_cover: broken\n"
        "templates:\n"
        "  - {name: broken, source: templates/resume.typ, kind: resume, page_limit: 2.0}\n"
    )

    with pytest.raises(RegistryError, match="broken"):
        load_registry(tmp_path)


def test_missing_source_file_names_entry_and_path(tmp_path):
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "registry.yaml").write_text(
        "default_resume: ghost\n"
        "default_cover: ghost\n"
        "templates:\n"
        "  - {name: ghost, source: templates/nope.typ, kind: resume, page_limit: 2}\n"
    )

    with pytest.raises(RegistryError, match="ghost") as exc_info:
        load_registry(tmp_path)
    assert "nope.typ" in str(exc_info.value)


def test_missing_registry_file_raises():
    with pytest.raises(RegistryError, match="registry.yaml"):
        load_registry(Path("/nonexistent-repo-root-for-test"))
