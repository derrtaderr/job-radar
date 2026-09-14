#!/usr/bin/env python3
"""calibrate — reads a season of resolved application outcomes and prints a
markdown report PROPOSING config changes a human then applies by hand.

There is no --apply flag and there will not be one. The whole value of this
tool is that it separates "the data says something" from "change the rules",
and a flag that collapsed the two would quietly turn a small sample into an
edit to the judgment layer. The report says so in its own closing line; this
docstring says so where someone would go looking to add the flag.

    python tools/calibrate.py tracker.md --config config --out calibration.md

`--archive` defaults to the config's own `archive_dir`, so the tool and the
radar cannot drift into two different answers about where applications live.

NOTE: this file and engine/loop/calibrate.py share a basename. The import
below stays fully qualified for that reason (house precedent: compile.py).
"""
import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    # Running as a script (`python tools/calibrate.py ...`) rather than
    # imported as `tools.calibrate` — put the repo root on sys.path so the
    # cross-package imports below resolve.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.loop.calibrate import DEFAULT_MIN_N, calibration_report
from engine.radar.config import ConfigError, load_config


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="calibrate",
        description="Turn resolved application outcomes into rule-tuning "
                    "proposals. Never edits config.")
    parser.add_argument("tracker_path", help="path to the tracker markdown file")
    parser.add_argument(
        "--archive", default=None,
        help="archive directory (default: the config's archive_dir)")
    parser.add_argument(
        "--min-n", type=int, default=DEFAULT_MIN_N, dest="min_n",
        help=f"minimum N on BOTH sides of a contrast before it may produce a "
             f"proposal (default: {DEFAULT_MIN_N}). Contrasts below the floor "
             f"are named in the suppressed section, never dropped.")
    parser.add_argument(
        "--config", default="config", help="config directory (default: config)")
    parser.add_argument(
        "--out", default=None,
        help="write the report to this file instead of printing it")
    args = parser.parse_args(argv)

    if args.min_n < 1:
        # Named for what it protects, not just what it forbids. A floor of
        # zero disables the only check standing between one person's hiring
        # decision and an edit to the judgment layer.
        print(f"--min-n must be at least 1, got {args.min_n} — it is the "
              f"minimum number of applications on each side of a contrast, "
              f"and it exists so a single application can never carry a "
              f"proposal", file=sys.stderr)
        return 1

    tracker_path = Path(args.tracker_path)
    try:
        tracker_text = tracker_path.read_text()
    except OSError as exc:
        print(f"cannot read tracker {tracker_path}: {exc}", file=sys.stderr)
        return 1

    try:
        cfg = load_config(Path(args.config))
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 1

    archive_dir = Path(args.archive) if args.archive else cfg.archive_dir

    report = calibration_report(tracker_text, archive_dir, cfg,
                                min_n=args.min_n)

    if args.out:
        Path(args.out).write_text(report)
        print(f"wrote {args.out}")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
