#!/usr/bin/env python3
"""network_cli — the only writer of config/network/.

The /paths and /reach session commands do the judgment (who to look up, what
to say). Everything they record comes through here, validated first, printed
before it is written, and skippable with --dry-run. Nothing here sends a
message; a touch is a record that the PERSON sent one.

    network_cli.py add    --company C --result found|none [--person "Name|Title|URL|role[|started]"]...
    network_cli.py touch  --company C [--posting ID] [--person SLUG] --state asked|applied|override ...
    network_cli.py reply  --company C --person SLUG --state replied|referred|declined|no_reply|left_company
    network_cli.py gate   COMPANY          exit 0 proceed, 3 ask first, 4 wait
    network_cli.py due                     what is waiting, oldest first; marks no_reply
    network_cli.py paths  COMPANY... | --tracker
"""
import argparse
import datetime
import sys
from pathlib import Path

if __package__ in (None, ""):
    # Running as a script rather than imported as `tools.network_cli` — put
    # the repo root on sys.path so the cross-package imports below resolve.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.loop.tracker_schema import parse_tracker
from engine.network.company import canonical, slugify
from engine.network.errors import NetworkError
from engine.network.flow import due, gate
from engine.network.network import load_network
from engine.network.paths import render_path_cell, resolve_paths
from engine.network.people import (
    ROLES, PeopleFile, Person, mark_left, parse_people, render_people,
    write_people)
from engine.network.touches import (
    HOOKS, PATH_KINDS, REGISTERS, Touch, append_touch, latest_by_person,
    load_touches, touch_row, validate_touch)
from engine.radar.config import ConfigError, load_config
from engine.radar.state import load_state

SEND_STATES = ("asked", "applied", "override")
REPLY_CHOICES = ("replied", "referred", "declined", "no_reply", "left_company")
DRAFTED_SECTION = "drafted but not applied"


def _parse_person(spec: str) -> Person:
    parts = [p.strip() for p in spec.split("|")]
    if len(parts) not in (4, 5):
        raise NetworkError(
            f"--person {spec!r} must be \"Name|Title|URL|role\" or "
            f"\"Name|Title|URL|role|started\", role one of {', '.join(ROLES)}")
    name, title, url, role = parts[:4]
    started = parts[4] if len(parts) == 5 else ""
    return Person(slug=slugify(name), name=name, title=title, url=url, role=role,
                  started=started, status="current")


def _touches_path(cfg):
    return cfg.network_dir / "touches.csv"


def _write(cfg, touch: Touch, dry_run: bool) -> None:
    problems = validate_touch(touch)
    if problems:
        raise NetworkError("; ".join(problems))
    print(("would append: " if dry_run else "appending: ") + touch_row(touch))
    if not dry_run:
        append_touch(_touches_path(cfg), touch)


def cmd_add(args, cfg, today) -> int:
    net = load_network(cfg.network_dir)
    pf = PeopleFile(company=args.company, looked_up=today, source=args.source,
                    result=args.result,
                    people=tuple(_parse_person(s) for s in args.person))
    parse_people(render_people(pf), f"--company {args.company}")  # validates
    print(render_people(pf))
    if args.dry_run:
        print("network: dry run, nothing written")
        return 0
    path = write_people(cfg.network_dir / "people", pf, net.aliases)
    print(f"network: {len(pf.people)} people for {args.company} -> {path}")
    return 0


def cmd_touch(args, cfg, today) -> int:
    if args.posting and args.posting not in load_state(cfg.state_file):
        print(f"network: no record of posting {args.posting!r} in {cfg.state_file}. "
              "Check the id against the queue, or leave --posting off to record "
              "the touch against the company alone")
        return 2
    _write(cfg, Touch(date=today.isoformat(), posting_id=args.posting,
                      company=args.company, person_slug=args.person,
                      path=args.path, motive=args.motive, hook_level=args.hook,
                      register=args.register, control=args.control,
                      state=args.state, note=args.note), args.dry_run)
    return 0


def cmd_reply(args, cfg, today) -> int:
    net = load_network(cfg.network_dir)
    key = (canonical(args.company, net.aliases), args.person)
    previous = latest_by_person(load_touches(_touches_path(cfg)),
                                net.aliases).get(key)
    if previous is None:
        print(f"network: no recorded touch to {args.person} at {args.company}. "
              "Record the send first with `touch --state asked`")
        return 2
    _write(cfg, Touch(date=today.isoformat(), posting_id=previous.posting_id,
                      company=previous.company, person_slug=args.person,
                      path=previous.path, motive=previous.motive,
                      hook_level=previous.hook_level, register=previous.register,
                      control=previous.control, state=args.state, note=args.note),
           args.dry_run)
    if args.state == "left_company" and not args.dry_run:
        pf = net.people.get(key[0])
        if pf is not None and args.person in {p.slug for p in pf.people}:
            write_people(cfg.network_dir / "people", mark_left(pf, args.person),
                         net.aliases)
            print(f"network: marked {args.person} as left_company in the "
                  f"{pf.company} people file")
    return 0


def cmd_gate(args, cfg, today) -> int:
    net = load_network(cfg.network_dir)
    result = gate(resolve_paths(args.company, net, today),
                  load_touches(_touches_path(cfg)), net.aliases, today)
    print(result.message)
    return result.code


def cmd_due(args, cfg, today) -> int:
    net = load_network(cfg.network_dir)
    touches = load_touches(_touches_path(cfg))
    reports = {canonical(c, net.aliases): resolve_paths(c, net, today)
               for c in {t.company for t in touches}}
    items, no_reply = due(touches, reports, net.aliases, today)
    for item in items:
        print(f"- {item.since}  {item.message}")
    if not items:
        print("network: nothing due")
    for t in no_reply:
        _write(cfg, t, args.dry_run)
    return 0


def _tracker_companies(cfg) -> list:
    if not cfg.tracker_path or not cfg.tracker_path.exists():
        raise NetworkError(
            "--tracker needs `tracker:` in settings.yaml to point at a file")
    table = parse_tracker(cfg.tracker_path.read_text()).get(DRAFTED_SECTION)
    if table is None:
        raise NetworkError(f"{cfg.tracker_path} has no '{DRAFTED_SECTION}' section")
    return [row.get("Company") for row in table.rows if row.get("Company")]


def cmd_paths(args, cfg, today) -> int:
    net = load_network(cfg.network_dir)
    companies = _tracker_companies(cfg) if args.tracker else args.companies
    if not companies:
        print("network: name at least one company, or pass --tracker")
        return 2
    if net.export_date:
        print(f"connections export dated {net.export_date.isoformat()}\n")
    print("| Company | Path |")
    print("|---|---|")
    for company in companies:
        cell = render_path_cell(resolve_paths(company, net, today)).replace("|", "\\|")
        print(f"| {company} | {cell} |")
    return 0


def _parser():
    parser = argparse.ArgumentParser(prog="network_cli",
                                     description="Record and read warm paths.")
    parser.add_argument("--config", default="./config", metavar="DIR")
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="write a company's people file")
    add.add_argument("--company", required=True)
    add.add_argument("--result", required=True, choices=("found", "none"))
    add.add_argument("--source", default="clay")
    add.add_argument("--person", action="append", default=[])
    add.add_argument("--dry-run", action="store_true")

    touch = sub.add_parser("touch",
                           help="record a send, an application, or an override")
    touch.add_argument("--company", required=True)
    touch.add_argument("--posting", default="")
    touch.add_argument("--person", default="")
    touch.add_argument("--path", default="", choices=PATH_KINDS)
    touch.add_argument("--motive", default="")
    touch.add_argument("--hook", default="", choices=HOOKS)
    touch.add_argument("--register", default="", choices=REGISTERS)
    touch.add_argument("--control", default="no", choices=("yes", "no"))
    touch.add_argument("--state", required=True, choices=SEND_STATES)
    touch.add_argument("--note", default="")
    touch.add_argument("--dry-run", action="store_true")

    reply = sub.add_parser("reply", help="record what came back")
    reply.add_argument("--company", required=True)
    reply.add_argument("--person", required=True)
    reply.add_argument("--state", required=True, choices=REPLY_CHOICES)
    reply.add_argument("--note", default="")
    reply.add_argument("--dry-run", action="store_true")

    g = sub.add_parser("gate", help="should /apply proceed for this company?")
    g.add_argument("company")

    d = sub.add_parser("due", help="what is waiting on you, oldest first")
    d.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("paths", help="print the path for companies")
    p.add_argument("companies", nargs="*")
    p.add_argument("--tracker", action="store_true",
                   help="every company in the tracker's drafted section")
    return parser


COMMANDS = {"add": cmd_add, "touch": cmd_touch, "reply": cmd_reply,
            "gate": cmd_gate, "due": cmd_due, "paths": cmd_paths}


def main(argv=None, today=None) -> int:
    args = _parser().parse_args(argv)
    today = today or datetime.date.today()
    try:
        cfg = load_config(Path(args.config))
    except ConfigError as exc:
        print(f"network: {exc}")
        return 2
    try:
        return COMMANDS[args.command](args, cfg, today)
    except NetworkError as exc:
        print(f"network: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
