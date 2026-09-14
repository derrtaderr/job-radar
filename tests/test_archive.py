"""Pin engine/loop/archive.py's contract:

- archive_application copies every file from an apply-out folder into
  archive_dir/<slug>/, writes outcome.md (frontmatter from meta + a
  seeded ## Log), and refuses (named error) if the slug already exists.
- read_outcome round-trips that frontmatter + log back into a dict.
- append_log adds a dated line, preserving every prior line untouched.
- bump_followup increments the frontmatter counter atomically and raises
  FollowupCapError the moment a bump would take it past the cap (2).

All fixture content is fictional (Acme Corp / Data Engineer) — never a
real application.
"""
import pytest
from pathlib import Path

from engine.loop.archive import (
    ArchiveError,
    FollowupCapError,
    archive_application,
    append_log,
    bump_followup,
    read_outcome,
)


def _make_apply_dir(tmp_path: Path, slug: str = "acme-data-engineer") -> Path:
    apply_dir = tmp_path / "apply-out" / slug
    apply_dir.mkdir(parents=True)
    (apply_dir / "resume.typ").write_text("#let name = \"Fictional Applicant\"\n")
    (apply_dir / "resume.pdf").write_bytes(b"%PDF-fake-resume")
    (apply_dir / "cover.typ").write_text("Dear Acme Corp,\n")
    (apply_dir / "cover.pdf").write_bytes(b"%PDF-fake-cover")
    (apply_dir / "jd.md").write_text("# Data Engineer at Acme Corp\n")
    return apply_dir


def _meta(**overrides) -> dict:
    base = {"company": "Acme Corp", "role": "Data Engineer", "applied": "2026-09-13"}
    base.update(overrides)
    return base


# --- archive_application: roundtrip -----------------------------------

def test_archive_application_copies_all_files(tmp_path):
    apply_dir = _make_apply_dir(tmp_path)
    archive_dir = tmp_path / "archive"

    dest = archive_application(apply_dir, archive_dir, _meta())

    assert dest == archive_dir / "acme-data-engineer"
    for name in ("resume.typ", "resume.pdf", "cover.typ", "cover.pdf", "jd.md"):
        assert (dest / name).exists()
    assert (dest / "resume.pdf").read_bytes() == b"%PDF-fake-resume"
    assert (dest / "outcome.md").exists()


def test_archive_application_copies_subdirectories_recursively(tmp_path):
    # A live extras/ subdir under apply_dir (e.g. saved job-posting screenshots
    # or research notes) must not vanish with zero signal when archived — the
    # archive is supposed to be a faithful record of what was applied with.
    apply_dir = _make_apply_dir(tmp_path)
    (apply_dir / "extras").mkdir()
    (apply_dir / "extras" / "notes.md").write_text("Fictional prep notes for Acme Corp.\n")
    (apply_dir / "extras" / "nested").mkdir()
    (apply_dir / "extras" / "nested" / "deep.txt").write_text("still here\n")
    archive_dir = tmp_path / "archive"

    dest = archive_application(apply_dir, archive_dir, _meta())

    assert (dest / "extras" / "notes.md").read_text() == "Fictional prep notes for Acme Corp.\n"
    assert (dest / "extras" / "nested" / "deep.txt").read_text() == "still here\n"


def test_archive_application_writes_frontmatter_from_meta(tmp_path):
    apply_dir = _make_apply_dir(tmp_path)
    archive_dir = tmp_path / "archive"

    dest = archive_application(apply_dir, archive_dir, _meta())
    outcome = read_outcome(dest)

    assert outcome["company"] == "Acme Corp"
    assert outcome["role"] == "Data Engineer"
    assert outcome["applied"] == "2026-09-13"
    assert outcome["followups"] == 0


def test_archive_application_seeds_log_with_applied_line(tmp_path):
    apply_dir = _make_apply_dir(tmp_path)
    archive_dir = tmp_path / "archive"

    dest = archive_application(apply_dir, archive_dir, _meta())
    outcome = read_outcome(dest)

    assert outcome["log"] == ["- 2026-09-13: applied"]


def test_archive_application_missing_meta_key_names_it(tmp_path):
    apply_dir = _make_apply_dir(tmp_path)
    archive_dir = tmp_path / "archive"
    meta = _meta()
    del meta["role"]

    with pytest.raises(ArchiveError, match="role"):
        archive_application(apply_dir, archive_dir, meta)


def test_archive_application_refuses_existing_slug(tmp_path):
    apply_dir = _make_apply_dir(tmp_path)
    archive_dir = tmp_path / "archive"
    archive_application(apply_dir, archive_dir, _meta())

    with pytest.raises(ArchiveError, match="acme-data-engineer"):
        archive_application(apply_dir, archive_dir, _meta())

    # the refusal must not have clobbered the first archive's files
    assert (archive_dir / "acme-data-engineer" / "outcome.md").exists()


# --- append_log: preserves prior lines ---------------------------------

def test_append_log_preserves_prior_lines(tmp_path):
    apply_dir = _make_apply_dir(tmp_path)
    archive_dir = tmp_path / "archive"
    dest = archive_application(apply_dir, archive_dir, _meta())

    append_log(dest, "2026-09-20", "sent followup #1")
    append_log(dest, "2026-09-27", "sent followup #2")

    outcome = read_outcome(dest)
    assert outcome["log"] == [
        "- 2026-09-13: applied",
        "- 2026-09-20: sent followup #1",
        "- 2026-09-27: sent followup #2",
    ]
    # frontmatter untouched by a log-only append
    assert outcome["company"] == "Acme Corp"
    assert outcome["followups"] == 0


# --- bump_followup: cap enforcement -------------------------------------

def test_bump_followup_increments_and_returns_new_count(tmp_path):
    apply_dir = _make_apply_dir(tmp_path)
    archive_dir = tmp_path / "archive"
    dest = archive_application(apply_dir, archive_dir, _meta())

    assert bump_followup(dest) == 1
    assert read_outcome(dest)["followups"] == 1


def test_bump_followup_second_bump_ok_at_cap(tmp_path):
    apply_dir = _make_apply_dir(tmp_path)
    archive_dir = tmp_path / "archive"
    dest = archive_application(apply_dir, archive_dir, _meta())

    bump_followup(dest)
    assert bump_followup(dest) == 2
    assert read_outcome(dest)["followups"] == 2


def test_bump_followup_third_bump_raises_cap_error(tmp_path):
    apply_dir = _make_apply_dir(tmp_path)
    archive_dir = tmp_path / "archive"
    dest = archive_application(apply_dir, archive_dir, _meta())

    bump_followup(dest)
    bump_followup(dest)
    with pytest.raises(FollowupCapError, match="2"):
        bump_followup(dest)

    # a raised cap must not have mutated the stored count
    assert read_outcome(dest)["followups"] == 2


def test_bump_followup_names_the_application_in_cap_error(tmp_path):
    apply_dir = _make_apply_dir(tmp_path)
    archive_dir = tmp_path / "archive"
    dest = archive_application(apply_dir, archive_dir, _meta())
    bump_followup(dest)
    bump_followup(dest)

    with pytest.raises(FollowupCapError, match="acme-data-engineer"):
        bump_followup(dest)
