#!/usr/bin/env python3
"""tracker_cli — validates a job-search tracker markdown file against the
header-driven contract (engine/loop/tracker_schema.py): the four known
sections and their required columns, ISO dates in the date columns, no
duplicate Company+Role within a section.

Violations are plain-English strings a human reads directly, not codes —
the CLI just prints them, same convention as tools/verify_pdf.py.
"""
import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    # Running as a script (`python tools/tracker_cli.py ...`) rather than
    # imported as `tools.tracker_cli` — put the repo root on sys.path so
    # the cross-package import below resolves.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.loop.tracker_schema import parse_tracker, tracker_check


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="tracker_cli",
        description="Validate a job-search tracker markdown file.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser(
        "check", help="check a tracker file against the header-driven contract")
    check_parser.add_argument("path", help="path to the tracker markdown file")

    args = parser.parse_args(argv)

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


if __name__ == "__main__":
    sys.exit(main())
