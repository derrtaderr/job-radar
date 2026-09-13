"""Seen-job memory. One file, one dict: job id → the ISO date the radar first
recorded it. That's the whole mechanism that keeps yesterday's postings out of
today's queue, which is why it is deliberately dumb and deliberately readable.

The state file lives under the user's gitignored config/ directory (see
settings.yaml), never in the repo — it is a record of one person's search.
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
