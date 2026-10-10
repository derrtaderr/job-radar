"""The touch ledger: every outreach message sent, every reply heard.

Append-only CSV under config/network/, the same shape as decisions.csv and
written through `csv` for the same reason (a company with a comma cannot
shift the columns). A later row for the same company and person supersedes an
earlier one; nothing is rewritten in place, so the history calibration reads
is the history that happened.

Unlike the decision ledger, a malformed row here is an ERROR, not a warning.
A skipped touch is a send that silently vanishes from the reply rates, and
those rates are the whole reason this file exists.
"""
from __future__ import annotations

import csv
import datetime
import io
from dataclasses import astuple, dataclass
from pathlib import Path

from engine.network.company import canonical
from engine.network.errors import NetworkError

COLUMNS = ("date", "posting_id", "company", "person_slug", "path", "motive",
           "hook_level", "register", "control", "state", "note")
STATES = ("asked", "replied", "referred", "declined", "no_reply",
          "left_company", "applied", "override")
REPLY_STATES = ("replied", "referred", "declined")
CLOSED_STATES = REPLY_STATES + ("no_reply", "left_company")
PATH_KINDS = ("warm", "recent_hire", "cold_hm", "none", "")
HOOKS = ("shared_history", "their_post", "build_match", "none", "")
REGISTERS = ("driver", "expressive", "steady", "analytical", "unclear", "")
_PERSONLESS_STATES = ("applied", "override")


@dataclass(frozen=True)
class Touch:
    date: str
    posting_id: str
    company: str
    person_slug: str
    path: str
    motive: str
    hook_level: str
    register: str
    control: str
    state: str
    note: str


def _named(values) -> str:
    return ", ".join(v for v in values if v)


def validate_touch(t: Touch) -> list:
    """Every problem with one row, in plain words. Empty means valid."""
    problems = []
    try:
        datetime.date.fromisoformat(t.date)
    except ValueError:
        problems.append(f"date {t.date!r} is not YYYY-MM-DD")
    if t.state not in STATES:
        problems.append(f"state {t.state!r} is not one of {_named(STATES)}")
    if not t.company.strip():
        problems.append("company is empty")
    if t.state not in _PERSONLESS_STATES and not t.person_slug.strip():
        problems.append(
            f"person_slug is empty, and a {t.state!r} row is about a person")
    if t.path not in PATH_KINDS:
        problems.append(f"path {t.path!r} is not one of {_named(PATH_KINDS)}")
    if t.hook_level not in HOOKS:
        problems.append(f"hook_level {t.hook_level!r} is not one of {_named(HOOKS)}")
    if t.register not in REGISTERS:
        problems.append(f"register {t.register!r} is not one of {_named(REGISTERS)}")
    if t.control not in ("yes", "no", ""):
        problems.append(f"control {t.control!r} must be yes or no")
    return problems


def parse_touches(text) -> tuple:
    """(touches, problems). Every problem names its line number."""
    lines = [line for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        return [], []
    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    missing = [c for c in COLUMNS if c not in (reader.fieldnames or ())]
    if missing:
        return [], [f"missing required column(s): {', '.join(missing)} "
                    f"(header must be: {','.join(COLUMNS)})"]
    touches, problems = [], []
    for line_no, raw in enumerate(reader, start=2):
        touch = Touch(**{c: (raw.get(c) or "").strip() for c in COLUMNS})
        row_problems = validate_touch(touch)
        if row_problems:
            problems.append(f"line {line_no}: {'; '.join(row_problems)}")
            continue
        touches.append(touch)
    return touches, problems


def load_touches(path) -> list:
    """Every touch, or NetworkError naming each bad line. A missing file is
    an empty ledger: nothing has been sent yet."""
    p = Path(path)
    if not p.exists():
        return []
    touches, problems = parse_touches(p.read_text())
    if problems:
        raise NetworkError(f"{p}: " + " | ".join(problems)
                           + " — fix the row by hand; nothing was skipped")
    return touches


def touch_row(touch: Touch) -> str:
    """The CSV line a touch is written as, for printing before a write."""
    buf = io.StringIO()
    csv.writer(buf).writerow(astuple(touch))
    return buf.getvalue().rstrip("\r\n")


def append_touch(path, touch: Touch) -> None:
    """Header written atomically with the first row via exclusive create, the
    same race-proofing as the decision ledger's append_decision."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    row = list(astuple(touch))
    try:
        with p.open("x", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(COLUMNS)
            writer.writerow(row)
        return
    except FileExistsError:
        pass
    with p.open("a", newline="") as f:
        writer = csv.writer(f)
        if f.tell() == 0:
            writer.writerow(COLUMNS)
        writer.writerow(row)


def latest_by_person(touches, aliases) -> dict:
    """{(canonical company, person_slug): newest Touch}. Newest by date, the
    later row breaking a tie, because the file's own order is its only
    tiebreak."""
    latest = {}
    for index, t in enumerate(touches):
        key = (canonical(t.company, aliases), t.person_slug)
        rank = (t.date, index)
        if key not in latest or rank >= latest[key][0]:
            latest[key] = (rank, t)
    return {key: t for key, (_, t) in latest.items()}
