"""Archive — files an application away once it's applied, into
archive_dir/<slug>/, and tracks its outcome over time.

archive_application copies everything an apply-out folder produced
(resume/cover .typ sources, their .pdf, jd.md) into the archive slug and
writes outcome.md: a small hand-rolled frontmatter block (company, role,
applied, followups) plus a `## Log` section seeded with one dated
"applied" line. Frontmatter is parsed and re-rendered by hand rather than
through PyYAML — the values here are always plain strings a person typed
(a date like `2026-09-13` would otherwise get silently promoted to a
datetime.date by PyYAML's implicit date resolver) and the set of keys is
small and fixed, so a full YAML round trip buys nothing but a type-
coercion surprise.

read_outcome/append_log/bump_followup are the read/write pair over that
same file: append_log adds a dated log line without disturbing any other
line (frontmatter or log), and bump_followup increments the `followups`
counter atomically (read, check the cap, rewrite the whole file) so a cap
violation raises before anything is written.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

FOLLOWUP_CAP = 2
_REQUIRED_META_KEYS = ("company", "role", "applied")
_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)
_LOG_HEADING = "## Log"


class ArchiveError(Exception):
    """Raised for anything wrong with archiving an application: missing
    meta, or a slug that's already archived. Always names the offending
    key or slug so fixing it is a one-line lookup."""


class FollowupCapError(Exception):
    """Raised when bump_followup would take an application's followup
    count past FOLLOWUP_CAP. Names the cap and the application."""


def _parse_frontmatter(text: str) -> tuple:
    """Return (frontmatter dict of raw strings, body text after the
    closing `---`). Order of keys is preserved (dict insertion order)
    so re-rendering doesn't shuffle the file."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise ArchiveError("outcome.md is missing its frontmatter block")
    frontmatter = {}
    for line in match.group(1).splitlines():
        if not line.strip():
            continue
        key, _, value = line.partition(":")
        frontmatter[key.strip()] = value.strip()
    return frontmatter, text[match.end():]


def _parse_log(body: str) -> list:
    """Every non-blank line under the `## Log` heading, in file order."""
    lines = body.splitlines()
    log = []
    in_log = False
    for line in lines:
        if line.strip() == _LOG_HEADING:
            in_log = True
            continue
        if in_log and line.strip():
            log.append(line.rstrip())
    return log


def _render_outcome(frontmatter: dict, log_lines: list) -> str:
    fm_block = "\n".join(f"{key}: {value}" for key, value in frontmatter.items())
    log_block = "\n".join(log_lines)
    return f"---\n{fm_block}\n---\n\n{_LOG_HEADING}\n{log_block}\n"


def archive_application(apply_dir: Path, archive_dir: Path, meta: dict) -> Path:
    """Copy `apply_dir`'s files into `archive_dir/<apply_dir.name>/` and
    write its outcome.md. `meta` must carry company/role/applied — a
    missing key raises ArchiveError naming it, before anything is
    written. Refuses (ArchiveError, naming the slug) if the destination
    already exists, so a second archive attempt can never clobber the
    first. Returns the new archive slug directory."""
    apply_dir = Path(apply_dir)
    archive_dir = Path(archive_dir)
    slug = apply_dir.name
    dest = archive_dir / slug

    if dest.exists():
        raise ArchiveError(f"archive slug {slug!r} already exists at {dest}")

    for key in _REQUIRED_META_KEYS:
        if not meta.get(key):
            raise ArchiveError(f"missing required meta key {key!r}")

    dest.mkdir(parents=True)
    for item in sorted(apply_dir.iterdir()):
        if item.is_file():
            shutil.copy2(item, dest / item.name)

    frontmatter = {
        "company": meta["company"],
        "role": meta["role"],
        "applied": meta["applied"],
        "followups": 0,
    }
    log_lines = [f"- {meta['applied']}: applied"]
    (dest / "outcome.md").write_text(_render_outcome(frontmatter, log_lines))
    return dest


def read_outcome(archive_slug_dir: Path) -> dict:
    """Frontmatter (as a dict, `followups` coerced to int) plus `log`
    (list of raw log lines) from an archived application's outcome.md."""
    text = (Path(archive_slug_dir) / "outcome.md").read_text()
    frontmatter, body = _parse_frontmatter(text)
    frontmatter["followups"] = int(frontmatter["followups"])
    frontmatter["log"] = _parse_log(body)
    return frontmatter


def append_log(archive_slug_dir: Path, date, line: str) -> None:
    """Append one dated line (`- {date}: {line}`) to outcome.md's Log
    section. Every prior line — frontmatter and log alike — comes back
    unchanged; only the new line is added."""
    path = Path(archive_slug_dir) / "outcome.md"
    frontmatter, body = _parse_frontmatter(path.read_text())
    log_lines = _parse_log(body)
    log_lines.append(f"- {date}: {line}")
    path.write_text(_render_outcome(frontmatter, log_lines))


def bump_followup(archive_slug_dir: Path) -> int:
    """Increment outcome.md's `followups` counter by one and return the
    new count. Raises FollowupCapError, naming the cap and the
    application, the moment a bump would take the count past
    FOLLOWUP_CAP — the file is left unwritten when that happens."""
    archive_slug_dir = Path(archive_slug_dir)
    path = archive_slug_dir / "outcome.md"
    frontmatter, body = _parse_frontmatter(path.read_text())
    log_lines = _parse_log(body)
    current = int(frontmatter["followups"])

    if current >= FOLLOWUP_CAP:
        raise FollowupCapError(
            f"followup cap ({FOLLOWUP_CAP}) reached for {archive_slug_dir.name!r} "
            f"— cannot bump past {current}")

    new_count = current + 1
    frontmatter["followups"] = str(new_count)
    path.write_text(_render_outcome(frontmatter, log_lines))
    return new_count
