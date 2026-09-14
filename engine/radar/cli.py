"""The command line — the only layer that touches the clock, the network, and
the filesystem. Everything below it is pure, which is why the interesting
failure modes can be tested here in full without a single real request.

Three ways to run:

    radar.py                    a normal run: scrape, judge, write the day folder
    radar.py --dry-run          load the config and run the pipeline on zero
                                rows; writes nothing. The smoke test.
    radar.py --check            re-check the postings your tracker says you are
                                waiting on, so you don't spend an application
                                hour on a role that already closed.
"""
from __future__ import annotations

import argparse
import datetime

from engine.radar.config import ConfigError, load_config
from engine.radar.pipeline import pipeline
from engine.radar.report import day_paths, write_jds, write_report
from engine.radar.state import load_state, save_state
from engine.radar.tracker import check_postings, closed_recent_companies, tracker_companies

_NO_SCRAPE = ("radar: scrape module not yet available (engine/radar/scrape.py) — "
              "this command needs it for network access")


def _parse(argv):
    parser = argparse.ArgumentParser(
        prog="radar", description="Deterministic job-search radar.")
    parser.add_argument("--config", default="./config", metavar="DIR",
                        help="config directory (default: ./config)")
    parser.add_argument("--check", action="store_true",
                        help="re-check tracked postings for liveness, then exit")
    parser.add_argument("--dry-run", action="store_true",
                        help="load config and run the pipeline on zero rows; writes nothing")
    return parser.parse_args(argv)


def _scrape_module():
    """Imported lazily and by name so the rest of the CLI stays usable — and
    testable — without the network layer or its heavy dependencies present."""
    import importlib

    return importlib.import_module("engine.radar.scrape")


UNSET, MISSING, FOUND = "unset", "missing", "found"


def _tracker_text(cfg):
    """(state, text) for the configured tracker.

    Three states, not two. "You never configured a tracker" and "you configured
    one and the file isn't there" look identical downstream — both yield no text
    — but they are different mistakes with different fixes, and only one of them
    is a mistake at all.
    """
    if not cfg.tracker_path:
        return UNSET, None
    if not cfg.tracker_path.exists():
        return MISSING, None
    return FOUND, cfg.tracker_path.read_text()


def _tracker_set(cfg, today):
    """Companies already in play: the active tracker sections, plus anyone whose
    application closed recently enough to still be a live conversation.

    A configured tracker that isn't on disk warns and returns nothing. The run
    continues, because a missing tracker must not take down the radar — but it
    must never be silent. Suppression failing quietly is exactly the failure
    mode the closed-window rule exists to prevent, and one typo in settings.yaml
    would otherwise cost every future run its suppression with no symptom.
    """
    state, text = _tracker_text(cfg)
    if state is MISSING:
        print(f"radar: WARNING — tracker configured as {cfg.tracker_path} but no file "
              "is there, so NOTHING is being suppressed this run (fix `tracker:` in "
              "settings.yaml, or set it to null if you don't keep one)")
    if text is None:
        return set()
    return (tracker_companies(text, cfg.tracker_active_sections)
            | closed_recent_companies(text, today, cfg.closed_window_days))


def _check(cfg, fetch_fn) -> int:
    state, text = _tracker_text(cfg)
    if state is MISSING:
        print(f"radar: --check needs the tracker, but no file is at {cfg.tracker_path} "
              "(fix `tracker:` in settings.yaml, or move the file back)")
        return 2
    if state is UNSET:
        print("radar: --check needs a tracker — set `tracker:` in settings.yaml "
              "to a markdown file of your applications")
        return 2

    if fetch_fn is None:
        try:
            fetch_fn = _scrape_module().http_fetch
        except ImportError:
            print(_NO_SCRAPE)
            return 2

    results = check_postings(text, fetch_fn, cfg.tracker_active_sections)
    if not results:
        print("liveness: no tracked postings carry a URL, nothing to check")
        return 0

    for r in results:
        print(f"  {r['status'].upper():8} {r['company']}  {r['url']}")
    live = [r for r in results if r["status"] == "live"]
    dead = [r for r in results if r["status"] == "dead"]
    unknown = [r for r in results if r["status"] == "unknown"]
    print(f"liveness: {len(live)} live, {len(dead)} dead, {len(unknown)} unknown "
          f"({len(results)} tracked)")
    if dead:
        print("DEAD (don't spend the application hour on these): "
              + ", ".join(r["company"] for r in dead))
    if unknown:
        # "unknown" is not a soft "dead". A bot wall or a rate limit means the
        # check learned nothing, and reporting it as dead would talk someone out
        # of a role that is still open.
        print("UNKNOWN means the check learned nothing (bot wall, rate limit, "
              "timeout). Treat as still open and verify by hand: "
              + ", ".join(r["company"] for r in unknown))
    return 0


def main(argv=None, scrape_fn=None, fetch_fn=None) -> int:
    """Returns a process exit code. 0 is a real, completed run."""
    args = _parse(argv or [])
    today = datetime.date.today()

    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        print(f"radar: {exc}")
        return 2

    if args.check:
        return _check(cfg, fetch_fn)

    if args.dry_run:
        # The smoke test: prove the config loads and the pipeline runs, and
        # touch nothing. Zero rows here is expected, not a broken scrape.
        survivors, killed, _ = pipeline([], {}, cfg, set(), today)
        print(f"radar: dry run — config OK ({len(cfg.queries)} queries, "
              f"{len(cfg.kill_rules)} kill rules), 0 rows in, "
              f"{len(survivors)} queued, {len(killed)} killed, nothing written")
        return 0

    if scrape_fn is None:
        try:
            scrape_fn = _scrape_module().scrape
        except ImportError:
            print(_NO_SCRAPE)
            return 2

    state = load_state(cfg.state_file)
    try:
        raw_rows = scrape_fn(cfg)
    except ImportError:
        # engine/radar/scrape.py imports cleanly without jobspy on the path —
        # the import is lazy, inside scrape() — so _scrape_module() above
        # never catches a missing jobspy. It only surfaces here, once the
        # scrape actually runs, and a stranger on system python deserves the
        # same friendly message as a missing scrape module, not a traceback.
        print(_NO_SCRAPE)
        return 2
    if not raw_rows:
        # Zero rows is a broken scrape, not a quiet day. Say so loudly and leave
        # state untouched, so a bad run can't poison the next one by recording
        # its non-event.
        print("radar: SCRAPE RETURNED 0 ROWS — treat as a broken scrape, not a "
              "quiet day (check the scraper and the job board)")
        return 1

    survivors, killed, new_state = pipeline(
        raw_rows, state, cfg, _tracker_set(cfg, today), today)

    _, queue_path, jd_dir = day_paths(cfg.output_dir, today)
    jds = write_jds(jd_dir, survivors, killed, str(today))
    if write_report(queue_path, survivors, killed, str(today)):
        print(f"radar: {len(raw_rows)} raw rows scraped, {len(survivors)} queued, "
              f"{len(killed)} killed, {jds} JDs saved → {queue_path}")
    else:
        print(f"radar: {len(raw_rows)} raw rows scraped, nothing new today "
              "(all seen, suppressed, or filtered)")

    save_state(new_state, cfg.state_file)
    return 0
