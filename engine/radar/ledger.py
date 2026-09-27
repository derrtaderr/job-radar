"""The decision ledger — the human's judgment, made machine-readable.

The engine kills and scores; the human reads the survivors' JDs and decides. That
decision used to have nowhere to go except prose in a markdown tracker nothing
parses, so the next run could not see it, and a req killed by hand came back
days later as the top-scored row.

This is a CSV in the user's gitignored `config/`, one row per decision, written
by `radar.py judge` and read by the pipeline before ranking. It is deliberately
NOT a suppression list. A judged posting that comes back renders in the queue
with its prior verdict attached, because the aggregator copy sometimes carries
detail the original lacked and because the human is the final gate — hiding a row
on the strength of a past decision is the same failure as forgetting the decision,
just quieter.

**Matching runs three tiers, and the order is load-bearing.** The live case that
motivated this came back under a NEW posting id: same company, same title, same
body, a new id because the board reissued the req. So:

1. exact `jid` — the cheap, certain case.
2. the normalised `(company, title)` pair — the reissued req.
3. the body fingerprint, via the earlier jid's entry in `state.json` — the
   aggregator repost, where the board's own name replaces the client's and tier 2
   cannot fire.

Tier 2 is why a ledger row carries company and title even when `judge` was called
with a jid alone.

**The newest decision wins.** The file is append-only, a person changes their mind,
and every tier picks the most recent matching row by date (later row breaks a tie).

**Tier 3 matches on the BODY fingerprint only.** The comp fingerprint is a band
plus a benefits set, which unrelated postings share; it is good enough to FLAG a
possible repost for a human to look at, and not good enough to speak for their
judgment about a company they have never seen.
"""
from __future__ import annotations

import csv
import datetime
import io
import re
from dataclasses import dataclass
from pathlib import Path

from engine.radar.fingerprint import fp_body, fp_comp, fp_equal
from engine.radar.state import fingerprints

COLUMNS = ("jid", "company", "title", "verdict", "reason", "date", "url")

# Closed and small on purpose. `kill` is the human's judgment ruling a posting
# out; `draft` is the human choosing to pursue it. A wider enum would invite
# "maybe", and a maybe is what the queue already is.
VERDICTS = ("kill", "draft")

# Corporate suffixes the two sides of a match write inconsistently — the scrape
# says "Northwind Analytics, Inc." one day and "Northwind Analytics" the next.
_SUFFIX = re.compile(
    r"[\s,]+(?:inc|inc\.|llc|l\.l\.c\.|ltd|ltd\.|corp|corp\.|corporation|co|co\.|"
    r"gmbh|plc|pbc|sa|ag|limited)$", re.I)
_NON_WORD = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class Decision:
    """One recorded judgment. Frozen because a decision is a historical fact —
    nothing downstream should be able to edit one in place."""

    jid: str
    company: str
    title: str
    verdict: str
    reason: str
    date: str
    url: str


def normalise_name(value) -> str:
    """The comparable form of a company or title: lower-cased, punctuation and
    repeated whitespace flattened, a trailing corporate suffix dropped.

    Deliberately NOT substring matching, which `tracker_suppresses` does use.
    The tracker's two sides are written by two different humans; both sides here
    are written by this tool, and a substring match on titles would collapse
    "Data Engineer" into "Data Engineering Manager" and carry a verdict onto a
    role the human never judged.
    """
    text = _SUFFIX.sub("", str(value or "").strip())
    return _NON_WORD.sub(" ", text.lower()).strip()


def parse_ledger(text) -> tuple:
    """(decisions, problems) for the ledger's text.

    Two return values rather than an exception, because the two callers want
    opposite things from a malformed file. A run wants every decision it can
    still read — one typo'd row must not cost the human every other judgment
    they recorded — while `tools/doctor.py` wants the problems named so they get
    fixed. Every problem names its line number and what is wrong with it.
    """
    lines = [line for line in str(text or "").splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    if not lines:
        return [], []

    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    missing = [c for c in COLUMNS if c not in (reader.fieldnames or ())]
    if missing:
        return [], [f"ledger is missing required column(s): {', '.join(missing)} "
                    f"(header must be: {','.join(COLUMNS)})"]

    decisions, problems = [], []
    for offset, raw in enumerate(reader, start=2):
        values = {c: (raw.get(c) or "").strip() for c in COLUMNS}
        if values["verdict"] not in VERDICTS:
            problems.append(
                f"ledger row {offset}: verdict {values['verdict']!r} is not one of "
                f"{', '.join(VERDICTS)}")
            continue
        if not (values["jid"] or values["company"] or values["title"]):
            problems.append(
                f"ledger row {offset}: needs a jid, or a company and title — a row "
                "with none of them can never match a posting")
            continue
        decisions.append(Decision(**values))
    return decisions, problems


def load_ledger(path) -> list:
    """Every readable decision, warning about the rows it had to skip.

    A missing file is an empty ledger, not an error: on day one nothing has been
    judged yet. Same instinct as `load_state` — a half-written judgment file must
    degrade loudly rather than take down a run.
    """
    p = Path(path)
    if not p.exists():
        return []
    decisions, problems = parse_ledger(p.read_text())
    for problem in problems:
        print(f"radar: WARNING — {p}: {problem}")
    return decisions


def append_decision(path, decision: Decision) -> None:
    """Append one decision, writing the header first if the file is new.

    Written through `csv` rather than by string join, so a company like
    "Northwind Analytics, Inc." cannot shift every column after it by one.
    """
    p = Path(path)
    new = not p.exists() or not p.read_text().strip()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", newline="") as f:
        writer = csv.writer(f)
        if new:
            writer.writerow(COLUMNS)
        writer.writerow([str(getattr(decision, c) or "") for c in COLUMNS])


def _recency_key(indexed):
    """Sort key picking the CURRENT decision out of several for one posting.

    The ledger is append-only and a person changes their mind, so two rows for one
    posting is the normal case rather than an error. The newest wins, by date, with
    the later ROW breaking a tie — an append-only file's own order is the only
    tiebreak it has. A date that will not parse sorts oldest rather than newest: a
    hand-edited or empty date must not silently become the current decision.
    """
    index, decision = indexed
    try:
        datetime.date.fromisoformat(decision.date[:10])
        date = decision.date[:10]
    except (ValueError, TypeError):
        date = ""
    return (date, index)


def _newest(matches):
    """The current decision among matches, or None when there are none."""
    return max(matches, key=_recency_key)[1] if matches else None


def current_decision_for(decisions, jid: str, company, title):
    """The decision already on file for this posting by id or by name, or None.

    Tiers 1 and 2 only — no fingerprints, because the caller is `judge`, which is
    recording a decision about a posting a human is looking at rather than matching
    a scraped row. Used to tell them what they are replacing: an append to an
    append-only file looks identical to a no-op otherwise, and they have no way to
    see the row that is about to stop being current.
    """
    indexed = list(enumerate(decisions))
    if jid:
        by_jid = [(i, d) for i, d in indexed if d.jid and d.jid == jid]
        if by_jid:
            return _newest(by_jid)
    pair = (normalise_name(company), normalise_name(title))
    if all(pair):
        by_pair = [(i, d) for i, d in indexed
                   if (normalise_name(d.company), normalise_name(d.title)) == pair]
        if by_pair:
            return _newest(by_pair)
    return None


def prior_verdict(row: dict, decisions, state, jid: str):
    """The decision this posting was already judged under, or None.

    Tiers run cheapest-and-most-certain first. Within a tier, several rows can
    match one posting, and the NEWEST one is the answer in every tier — tier 1 used
    to return the last row and tiers 2 and 3 the first, so one posting reported
    "draft" when it came back under its own id and "kill" when it came back
    reissued. Whichever rule is right, the tiers have to agree.

    Tier 1 and tier 2 are exact within themselves. Tier 3 carries a verdict only on
    `fp_body` equality — see the note there.
    """
    if not decisions:
        return None
    indexed = list(enumerate(decisions))

    by_jid = [(i, d) for i, d in indexed if d.jid and d.jid == jid]
    if by_jid:
        return _newest(by_jid)

    pair = (normalise_name(row.get("company")), normalise_name(row.get("title")))
    if all(pair):
        by_pair = [(i, d) for i, d in indexed
                   if (normalise_name(d.company), normalise_name(d.title)) == pair]
        if by_pair:
            return _newest(by_pair)

    # Tier 3 uses the BODY fingerprint only, never the comp one. A comp band plus
    # the common medical/dental/vision/401k/PTO set is shared by unrelated
    # postings, so inheriting a verdict through it told a person they had already
    # killed a company they had never seen. The comp fingerprint still earns the
    # `repost_of` FLAG in the pipeline, where a human reads it and decides; it is
    # not enough to speak for their judgment.
    row_body = fp_body(row)
    by_body = []
    for i, d in indexed:
        if not d.jid:
            continue
        _, prior_body = fingerprints(state.get(d.jid))
        if fp_equal(prior_body, row_body):
            by_body.append((i, d))
    return _newest(by_body)
