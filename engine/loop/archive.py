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

Archiving is all-or-nothing: the copy is staged into a temporary
directory inside archive_dir and renamed into place only once every file
has landed, so a failure partway through leaves no slug directory at all.
The alternative — create the destination, then copy into it — fails in
the worst possible shape, because the slug directory IS the record that
this application was archived. A half-copy would leave a husk that every
later attempt refuses as "already exists", permanently blocking an
application from being archived on the strength of a failure that
archived nothing.

read_outcome/append_log/bump_followup are the read/write pair over that
same file: append_log adds a dated log line without disturbing any other
line (frontmatter or log), and bump_followup increments the `followups`
counter atomically (read, check the cap, rewrite the whole file) so a cap
violation raises before anything is written.

Every failure this module can hit is something a person caused and can
fix in one line — a cleared apply-out folder, a hand-edit that dropped a
frontmatter key. So they all raise ArchiveError naming the path or the
value, never a bare FileNotFoundError/KeyError/ValueError, which reads as
a bug in the tool and sends the reader into this file instead of at their
own outcome.md.
"""
from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

FOLLOWUP_CAP = 2
_REQUIRED_META_KEYS = ("company", "role", "applied")
_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)
_LOG_HEADING = "## Log"


class ArchiveError(Exception):
    """Raised for anything wrong with archiving an application or reading
    one back: missing meta, a slug that's already archived, an apply-out
    folder that isn't there, or an outcome.md a hand-edit has broken.
    Always names the offending key, slug, path, or value so fixing it is
    a one-line lookup."""


class FollowupCapError(Exception):
    """Raised when bump_followup would take an application's followup
    count past FOLLOWUP_CAP. Names the cap and the application."""


def _parse_frontmatter(text: str, path=None) -> tuple:
    """Return (frontmatter dict of raw strings, body text after the
    closing `---`). Order of keys is preserved (dict insertion order)
    so re-rendering doesn't shuffle the file. `path` is only used to name
    the file in the error, since every caller already knows it and the
    reader needs it to go fix the right one."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise ArchiveError(
            f"{path or 'outcome.md'} is missing its frontmatter block "
            f"(the `---` fenced key: value lines at the very top)")
    frontmatter = {}
    for line in match.group(1).splitlines():
        if not line.strip():
            continue
        key, _, value = line.partition(":")
        frontmatter[key.strip()] = value.strip()
    return frontmatter, text[match.end():]


def _followups(frontmatter: dict, path) -> int:
    """The `followups` counter as an int, or an ArchiveError naming the
    file and what is wrong with it. Both failures here are hand-edits: a
    dropped key, or a value written as a word."""
    if "followups" not in frontmatter:
        raise ArchiveError(
            f"{path} has no `followups` key in its frontmatter — add "
            f"`followups: 0` (or the number of follow-ups already sent)")
    raw = frontmatter["followups"]
    try:
        return int(raw)
    except ValueError:
        raise ArchiveError(
            f"{path} has a non-numeric `followups` value ({raw!r}) — it "
            f"counts follow-ups, so it must be a whole number") from None


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
    """Copy `apply_dir`'s contents into `archive_dir/<apply_dir.name>/` and
    write its outcome.md. Files are copied as-is; subdirectories are
    copied recursively (shutil.copytree) — the archive is supposed to be
    a faithful mirror of apply-out, so nothing under apply_dir is allowed
    to vanish silently. `meta` must carry company/role/applied — a
    missing key raises ArchiveError naming it, before anything is
    written. Refuses (ArchiveError, naming the slug) if the destination
    already exists, so a second archive attempt can never clobber the
    first, and refuses (naming the path) if `apply_dir` isn't there at
    all. Returns the new archive slug directory.

    ALL OR NOTHING. Everything is copied into a temporary directory
    alongside the destination and renamed into place only after the last
    write succeeds, so a failure partway through leaves no slug directory
    and no litter — the next attempt starts clean instead of meeting a
    husk it has to refuse. The staging directory is created INSIDE
    archive_dir so the final step is a same-filesystem rename, which is
    atomic; staging under the system temp dir would silently degrade that
    rename to a copy and reopen the partial-write window this closes."""
    apply_dir = Path(apply_dir)
    archive_dir = Path(archive_dir)
    slug = apply_dir.name
    dest = archive_dir / slug

    if dest.exists():
        raise ArchiveError(f"archive slug {slug!r} already exists at {dest}")

    for key in _REQUIRED_META_KEYS:
        if not meta.get(key):
            raise ArchiveError(f"missing required meta key {key!r}")

    if not apply_dir.is_dir():
        raise ArchiveError(
            f"nothing to archive: {apply_dir} does not exist. An "
            f"application whose apply-out folder is gone cannot be archived "
            f"faithfully — record the outcome without an archive rather "
            f"than rebuilding one from materials that may not be what was "
            f"submitted")

    # Whether archive_dir already existed decides whether a failure may
    # remove it: created here and now is ours to clean up, pre-existing is
    # the human's tree and stays.
    archive_dir_existed = archive_dir.exists()
    archive_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(dir=archive_dir, prefix=f".{slug}.",
                                    suffix=".tmp"))
    try:
        for item in sorted(apply_dir.iterdir()):
            if item.is_dir():
                shutil.copytree(item, staging / item.name)
            else:
                shutil.copy2(item, staging / item.name)

        frontmatter = {
            "company": meta["company"],
            "role": meta["role"],
            "applied": meta["applied"],
            "followups": 0,
        }
        log_lines = [f"- {meta['applied']}: applied"]
        (staging / "outcome.md").write_text(
            _render_outcome(frontmatter, log_lines))

        # os.rename semantics: fails rather than merges if `dest` appeared
        # between the check above and here, which is the right answer.
        staging.rename(dest)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        if not archive_dir_existed:
            try:
                archive_dir.rmdir()
            except OSError:
                pass  # not empty — something else lives there, leave it
        raise

    return dest


def read_outcome(archive_slug_dir: Path) -> dict:
    """Frontmatter (as a dict, `followups` coerced to int) plus `log`
    (list of raw log lines) from an archived application's outcome.md.
    A frontmatter block that is missing, or missing/mangling `followups`,
    raises ArchiveError naming this file."""
    path = Path(archive_slug_dir) / "outcome.md"
    frontmatter, body = _parse_frontmatter(path.read_text(), path)
    frontmatter["followups"] = _followups(frontmatter, path)
    frontmatter["log"] = _parse_log(body)
    return frontmatter


def append_log(archive_slug_dir: Path, date, line: str) -> None:
    """Append one dated line (`- {date}: {line}`) to outcome.md's Log
    section. Every prior line — frontmatter and log alike — comes back
    unchanged; only the new line is added."""
    path = Path(archive_slug_dir) / "outcome.md"
    frontmatter, body = _parse_frontmatter(path.read_text(), path)
    log_lines = _parse_log(body)
    log_lines.append(f"- {date}: {line}")
    path.write_text(_render_outcome(frontmatter, log_lines))


def bump_followup(archive_slug_dir: Path) -> int:
    """Increment outcome.md's `followups` counter by one and return the
    new count. Raises FollowupCapError, naming the cap and the
    application, the moment a bump would take the count past
    FOLLOWUP_CAP — the file is left unwritten when that happens. A
    broken outcome.md raises ArchiveError naming the file, same as
    read_outcome."""
    archive_slug_dir = Path(archive_slug_dir)
    path = archive_slug_dir / "outcome.md"
    frontmatter, body = _parse_frontmatter(path.read_text(), path)
    log_lines = _parse_log(body)
    current = _followups(frontmatter, path)

    if current >= FOLLOWUP_CAP:
        raise FollowupCapError(
            f"followup cap ({FOLLOWUP_CAP}) reached for {archive_slug_dir.name!r} "
            f"— cannot bump past {current}")

    new_count = current + 1
    frontmatter["followups"] = str(new_count)
    path.write_text(_render_outcome(frontmatter, log_lines))
    return new_count
