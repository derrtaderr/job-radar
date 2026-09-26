"""Seen-job memory. One file, one dict: job id → what the radar recorded about
it the first time it saw it. That's the whole mechanism that keeps yesterday's
postings out of today's queue, which is why it is deliberately dumb and
deliberately readable.

The state file lives under the user's gitignored config/ directory (see
settings.yaml), never in the repo — it is a record of one person's search.

**Two entry shapes, one reader.** The value used to be a bare ISO date string.
It is now a dict carrying that date plus the company and title the run saw and
the two content fingerprints that let a repost be recognised across days (see
engine/radar/fingerprint.py). The reader still accepts the legacy string,
because a real user's state file predates this change and the alternative — not
recognising their own history — would re-queue their entire search on the first
run after an upgrade. So nothing reaches into an entry directly; everything goes
through the accessors below, and a legacy entry honestly reports "I don't know"
(None) for every field except its date rather than having one invented for it.
A None fingerprint must therefore never be treated as matching another None.
"""
from __future__ import annotations

import json
from pathlib import Path


def load_state(path) -> dict:
    """Read the seen-job map, or an empty one when there isn't a file yet.

    A corrupt file is a warning and an empty state, never an exception. Crashing
    here would take down a whole run over a half-written JSON file, and the worst
    a reset costs is one day of postings re-queued — far cheaper than a radar
    that refuses to run.
    """
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        print(f"radar: WARNING — {p} is corrupt JSON, starting from empty state")
        return {}


def save_state(state, path) -> None:
    """Write the seen-job map. Sorted keys and a trailing newline so the file
    diffs cleanly for a human reading it, instead of reshuffling every run."""
    Path(path).write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")


def make_entry(seen, company=None, title=None, fp_comp=None, fp_body=None) -> dict:
    """One state entry. Keys whose value is None are left OUT rather than
    written as nulls, so the file a human diffs stays as short as what the run
    actually learned — a posting with no comp band and no benefits block has no
    comp fingerprint, and saying so with an absent key reads better than a
    column of nulls."""
    entry = {"seen": str(seen)}
    for key, value in (("company", company), ("title", title),
                       ("fp_comp", fp_comp), ("fp_body", fp_body)):
        if value is not None:
            entry[key] = value
    return entry


def seen_date(entry):
    """The ISO date an entry was first recorded, whichever shape it is in."""
    if isinstance(entry, dict):
        return entry.get("seen")
    return entry


def entry_field(entry, name):
    """One named field of an entry, or None when this entry cannot know it.

    A legacy string entry carries only a date, so every other field is None —
    never a guess. A ledger row must not be able to match a posting on a field
    no run ever recorded.
    """
    return entry.get(name) if isinstance(entry, dict) else None


def fingerprints(entry) -> tuple:
    """(fp_comp, fp_body) for an entry. Both None for a legacy entry."""
    return entry_field(entry, "fp_comp"), entry_field(entry, "fp_body")
