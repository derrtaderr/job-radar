"""The command line — the only layer that touches the clock, the network, and
the filesystem. Everything below it is pure, which is why the interesting
failure modes can be tested here in full without a single real request.

Four ways to run:

    radar.py                    a normal run: scrape, judge, write the day folder
    radar.py --dry-run          load the config and run the pipeline on zero
                                rows; writes nothing. The smoke test.
    radar.py --check            re-check the postings your tracker says you are
                                waiting on, so you don't spend an application
                                hour on a role that already closed.
    radar.py judge <jid> ...    record the decision you just made about a
                                posting, so the next run can see it.

`judge` is a subcommand rather than another flag because it is the one verb here
that WRITES your judgment rather than reading it. It is dispatched on argv before
argparse sees anything, so no existing invocation changes shape.
"""
from __future__ import annotations

import argparse
import datetime

from engine.radar.config import ConfigError, load_config
from engine.radar.ledger import (
    VERDICTS,
    Decision,
    append_decision,
    current_decision_for,
    load_ledger,
)
from engine.radar.pipeline import pipeline
from engine.radar.report import day_paths, write_jds, write_report
from engine.radar.state import entry_field, load_state, save_state
from engine.radar.tracker import check_postings, closed_recent_companies, tracker_companies

_NO_SCRAPE = ("radar: scrape module not yet available (engine/radar/scrape.py) — "
              "this command needs it for network access")


_JUDGE_HELP = """\
The `judge` subcommand records a decision you made about a posting:

  radar.py judge <jid> --verdict kill  --reason bi-analytics
  radar.py judge <jid> --verdict draft --reason strong-fit
  radar.py judge --company "..." --title "..." --verdict kill --reason ...

It writes config/decisions.csv, which every later run reads: a judged posting
comes back with that verdict in the queue's Prior column rather than as a fresh
row. Run `radar.py judge --help` for its own options.
"""


def _parse(argv):
    parser = argparse.ArgumentParser(
        prog="radar", description="Deterministic job-search radar.",
        epilog=_JUDGE_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="./config", metavar="DIR",
                        help="config directory (default: ./config)")
    parser.add_argument("--check", action="store_true",
                        help="re-check tracked postings for liveness, then exit")
    parser.add_argument("--dry-run", action="store_true",
                        help="load config and run the pipeline on zero rows; writes nothing")
    return parser.parse_args(argv)


def _parse_judge(argv):
    parser = argparse.ArgumentParser(
        prog="radar judge",
        description="Record your decision about a posting in the decision ledger.")
    parser.add_argument("jid", nargs="?", default="",
                        help="the posting id, as the queue's JD link names it")
    parser.add_argument("--verdict", required=True, choices=VERDICTS,
                        help="kill (your judgment ruled it out) or draft (you are pursuing it)")
    parser.add_argument("--reason", required=True, metavar="SLUG",
                        help="a short slug you will recognise later, e.g. bi-analytics")
    parser.add_argument("--company", default="", help="overrides what state.json remembers")
    parser.add_argument("--title", default="", help="overrides what state.json remembers")
    parser.add_argument("--url", default="", help="the posting URL, if you have it")
    parser.add_argument("--config", default="./config", metavar="DIR",
                        help="config directory (default: ./config)")
    return parser.parse_args(argv)


def _judge(argv) -> int:
    """Append one decision to the ledger. Returns a process exit code.

    Company and title are backfilled from `state.json` when they were not passed,
    because the ledger's second matching tier is the normalised (company, title)
    pair — and that is the tier that catches a req reissued under a new posting
    id, which is the miss this whole command exists for. A row written by jid
    alone with those columns empty would only ever match tier 1, the tier that
    already missed.
    """
    args = _parse_judge(argv)

    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        print(f"radar: {exc}")
        return 2

    state = load_state(cfg.state_file)
    known = args.jid in state if args.jid else False
    entry = state.get(args.jid) if args.jid else None
    company = args.company or (entry_field(entry, "company") or "")
    title = args.title or (entry_field(entry, "title") or "")

    # BOTH a company and a title, always. A row carrying only one of them can only
    # ever match on the exact id — and tier 1 is the tier that already let the
    # reissued req through, which is the whole reason this command exists. A row
    # that cannot do its job is worse than no row, because it looks recorded.
    if not (company and title):
        missing = " and ".join(
            flag for flag, value in (("--company", company), ("--title", title))
            if not value)
        if args.jid and known:
            # The id IS on file, as an entry written before entries carried a
            # company and title. "No record of it" would be false, and it would
            # send someone to re-check an id that was right all along.
            print(f"radar: {args.jid!r} is in {cfg.state_file}, but its entry "
                  "predates the company and title a ledger row needs (it was "
                  "written before this machine recorded them). Pass "
                  f"{missing} to record the decision.")
        elif args.jid:
            print(f"radar: judge doesn't recognise the id {args.jid!r} — this "
                  f"machine has no record of it in {cfg.state_file}. Pass "
                  f"{missing} to record the decision anyway, or check the id "
                  "against today's queue.")
        else:
            # No id at all: naming only the half they left out reads as though the
            # other half were optional. The pair is the unit.
            print("radar: judge needs something to match a posting on — give a jid "
                  "from the queue, or both --company and --title")
        return 2

    # What this decision replaces, said out loud. The ledger is append-only and a
    # person changes their mind, so a second row is a normal day — but a silent
    # append is indistinguishable from a no-op, and the row about to stop being
    # current is invisible unless something names it.
    previous = current_decision_for(load_ledger(cfg.decisions_path), args.jid,
                                    company, title)
    if previous is not None:
        print(f"radar: already judged {previous.date} as {previous.verdict} "
              f"({previous.reason}); recording the newer decision — the newest row "
              "wins from now on")

    decision = Decision(jid=args.jid, company=company, title=title,
                        verdict=args.verdict, reason=args.reason,
                        date=str(datetime.date.today()), url=args.url)
    append_decision(cfg.decisions_path, decision)
    print(f"radar: recorded {args.verdict} ({args.reason}) for "
          f"{company or args.jid}{' — ' + title if title else ''} "
          f"-> {cfg.decisions_path}")
    return 0


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
    argv = list(argv or [])
    if argv and argv[0] == "judge":
        return _judge(argv[1:])

    args = _parse(argv)
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
        # Still call _tracker_set — a configured-but-missing tracker prints
        # its WARNING there, and a smoke test that reports "config OK" while
        # suppression is silently dead is worse than no smoke test at all.
        survivors, killed, _ = pipeline([], {}, cfg, _tracker_set(cfg, today), today,
                                        decisions=load_ledger(cfg.decisions_path))
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
    except ImportError as e:
        # engine/radar/scrape.py imports cleanly without jobspy on the path —
        # the import is lazy, inside scrape() — so _scrape_module() above
        # never catches a missing jobspy. It only surfaces here, once the
        # scrape actually runs, and a stranger on system python deserves the
        # same friendly message as a missing scrape module, not a traceback —
        # but the friendly message ALONE is misleading if the real cause is
        # some other missing dependency, so the underlying text rides along.
        print(f"{_NO_SCRAPE}\n  underlying import error: {e}")
        return 2
    if not raw_rows:
        # Zero rows is a broken scrape, not a quiet day. Say so loudly and leave
        # state untouched, so a bad run can't poison the next one by recording
        # its non-event.
        print("radar: SCRAPE RETURNED 0 ROWS — treat as a broken scrape, not a "
              "quiet day (check the scraper and the job board)")
        return 1

    survivors, killed, new_state = pipeline(
        raw_rows, state, cfg, _tracker_set(cfg, today), today,
        decisions=load_ledger(cfg.decisions_path))

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
