#!/usr/bin/env python3
"""tracker_cli — validates and edits a job-search tracker markdown file
against the header-driven contract (engine/loop/tracker_schema.py): the
four known sections and their required columns, ISO dates in the date
columns, no duplicate Company+Role within a section.

`check` reports violations as plain-English strings a human reads
directly, not codes — same convention as tools/verify_pdf.py. `add`,
`move`, and `touch` (engine/loop/tracker_edit.py) mutate the file: each
prints a unified diff of the change before writing, writes atomically
(temp file + rename, so a crash mid-write can never leave a half-written
tracker), and `--dry-run` prints the diff without touching the file.
"""
import argparse
import difflib
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

if __package__ in (None, ""):
    # Running as a script (`python tools/tracker_cli.py ...`) rather than
    # imported as `tools.tracker_cli` — put the repo root on sys.path so
    # the cross-package import below resolves.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.loop.followup import stale_active
from engine.loop.tracker_edit import TrackerEditError, add_row, move_row, touch_row
from engine.loop.tracker_schema import parse_tracker, tracker_check
from engine.radar.config import load_config

_DEFAULT_FOLLOWUP_AFTER_DAYS = 10


def _parse_set_args(pairs) -> dict:
    values = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise SystemExit(f"invalid --set value (expected KEY=VALUE): {pair!r}")
        key, _, value = pair.partition("=")
        values[key] = value
    return values


def _print_diff(old_text: str, new_text: str, path: Path) -> None:
    diff = difflib.unified_diff(
        old_text.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile=str(path), tofile=str(path))
    sys.stdout.writelines(diff)


def _print_stale_report(stale: list, unknown_touch: list, days: int) -> None:
    """Print the stale-rows table and the unknown-touch list. Always exits
    0 upstream (stale rows are information a person acts on, not an
    error) — this only formats what stale_active found."""
    if stale:
        print(f"stale ({days}+ days quiet):")
        for row in stale:
            print(f"  {row.company} — {row.role} — {row.days_quiet}d quiet "
                  f"(last touch {row.last_touch.isoformat()}) — "
                  f"stage: {row.stage or '(none)'} — next: {row.next_step or '(none)'}")
    else:
        print(f"stale ({days}+ days quiet): none")

    if unknown_touch:
        print("unknown touch (no parseable Last-touch date):")
        for row, reason in unknown_touch:
            company = row.get("Company") or "(no company)"
            role = row.get("Role") or "(no role)"
            print(f"  {company} — {role} — {reason}")
    else:
        print("unknown touch: none")


def _atomic_write(path: Path, text: str) -> None:
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def _apply_edit(path: Path, dry_run: bool, edit_fn) -> int:
    """Read the tracker, run `edit_fn(old_text) -> new_text`, print the
    diff, and write atomically unless `dry_run`. Shared by add/move/touch
    so all three carry the same diff-then-write-then-refuse-cleanly shape."""
    old_text = path.read_text()
    try:
        new_text = edit_fn(old_text)
    except TrackerEditError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    _print_diff(old_text, new_text, path)
    if not dry_run:
        _atomic_write(path, new_text)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="tracker_cli",
        description="Validate and edit a job-search tracker markdown file.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser(
        "check", help="check a tracker file against the header-driven contract")
    check_parser.add_argument("path", help="path to the tracker markdown file")

    add_parser = subparsers.add_parser(
        "add", help="append a row to a section's table")
    add_parser.add_argument("path")
    add_parser.add_argument("--section", required=True)
    add_parser.add_argument("--set", action="append", default=[],
                             metavar="KEY=VALUE", dest="set_")
    add_parser.add_argument("--dry-run", action="store_true")

    move_parser = subparsers.add_parser(
        "move", help="move one row from one section to another")
    move_parser.add_argument("path")
    move_parser.add_argument("--company", required=True)
    move_parser.add_argument("--role", required=True)
    move_parser.add_argument("--from", dest="from_section", required=True)
    move_parser.add_argument("--to", dest="to_section", required=True)
    move_parser.add_argument("--set", action="append", default=[],
                              metavar="KEY=VALUE", dest="set_")
    move_parser.add_argument("--dry-run", action="store_true")

    touch_parser = subparsers.add_parser(
        "touch", help="update one cell in one row")
    touch_parser.add_argument("path")
    touch_parser.add_argument("--section", required=True)
    touch_parser.add_argument("--company", required=True)
    touch_parser.add_argument("--role", required=True)
    touch_parser.add_argument("--column", required=True)
    touch_parser.add_argument("--value", required=True)
    touch_parser.add_argument("--dry-run", action="store_true")

    stale_parser = subparsers.add_parser(
        "stale", help="scan the Active section for rows that have gone quiet")
    stale_parser.add_argument("path")
    stale_parser.add_argument("--days", type=int, default=None,
                               help="days quiet to count as stale; default is "
                                    "the config's followup_after_days if --config "
                                    "is given, else 10")
    stale_parser.add_argument("--today", default=None,
                               help="YYYY-MM-DD; defaults to today's date")
    stale_parser.add_argument("--config", default=None,
                               help="config dir to read followup_after_days from "
                                    "when --days is not given")

    args = parser.parse_args(argv)

    if args.command == "check":
        text = Path(args.path).read_text()
        violations = tracker_check(text)

        if violations:
            for violation in violations:
                print(violation)
            return 1

        sections = parse_tracker(text)
        n_rows = sum(len(table.rows) for table in sections.values())
        k_sections = len(sections)
        print(f"tracker: OK ({n_rows} rows across {k_sections} sections)")
        return 0

    path = Path(args.path)

    if args.command == "add":
        values = _parse_set_args(args.set_)
        return _apply_edit(
            path, args.dry_run,
            lambda text: add_row(text, args.section, values))

    if args.command == "move":
        extra = _parse_set_args(args.set_)
        return _apply_edit(
            path, args.dry_run,
            lambda text: move_row(text, args.company, args.role,
                                   args.from_section, args.to_section, extra))

    if args.command == "touch":
        return _apply_edit(
            path, args.dry_run,
            lambda text: touch_row(text, args.section, args.company,
                                    args.role, args.column, args.value))

    if args.command == "stale":
        if args.days is not None:
            days = args.days
        elif args.config:
            days = load_config(Path(args.config)).followup_after_days
        else:
            days = _DEFAULT_FOLLOWUP_AFTER_DAYS

        today = date.fromisoformat(args.today) if args.today else date.today()

        text = path.read_text()
        stale, unknown_touch = stale_active(text, today, days)
        _print_stale_report(stale, unknown_touch, days)
        return 0

    raise AssertionError(f"unhandled command: {args.command!r}")  # argparse guards this


if __name__ == "__main__":
    sys.exit(main())
