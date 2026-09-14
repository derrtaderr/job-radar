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


# --- frontmatter parsing edge cases (pinned, behavior already correct) -----
# _parse_frontmatter splits on the FIRST colon only (str.partition), so a
# value that itself contains a colon must survive a full round trip rather
# than getting truncated at its own embedded ":".

def test_frontmatter_value_with_colon_round_trips(tmp_path):
    apply_dir = _make_apply_dir(tmp_path, slug="acme-revops")
    archive_dir = tmp_path / "archive"
    dest = archive_application(apply_dir, archive_dir, _meta(role="RevOps: Growth"))

    assert read_outcome(dest)["role"] == "RevOps: Growth"

    bump_followup(dest)
    assert read_outcome(dest)["role"] == "RevOps: Growth"


def test_unknown_frontmatter_key_survives_append_log_and_bump_followup(tmp_path):
    # An unknown key (e.g. added by hand, or by a future feature this module
    # doesn't know about) must not be dropped or reordered by either write
    # path — append_log and bump_followup only ever touch the field they
    # own.
    apply_dir = _make_apply_dir(tmp_path)
    archive_dir = tmp_path / "archive"
    dest = archive_application(apply_dir, archive_dir, _meta())

    path = dest / "outcome.md"
    text = path.read_text().replace("followups: 0\n---", "followups: 0\nsource: outbound\n---")
    path.write_text(text)

    expected_prefix = ["company: Acme Corp", "role: Data Engineer", "applied: 2026-09-13"]

    append_log(dest, "2026-09-20", "sent followup #1")
    outcome = read_outcome(dest)
    assert outcome["source"] == "outbound"
    fm_lines = path.read_text().splitlines()
    assert fm_lines[1:6] == expected_prefix + ["followups: 0", "source: outbound"]

    bump_followup(dest)
    outcome = read_outcome(dest)
    assert outcome["source"] == "outbound"
    assert outcome["followups"] == 1
    fm_lines = path.read_text().splitlines()
    assert fm_lines[1:6] == expected_prefix + ["followups: 1", "source: outbound"]
