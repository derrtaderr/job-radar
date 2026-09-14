"""Calibration — turns resolved application outcomes into rule-tuning
PROPOSALS, and never into a config edit.

This is the only module in the engine that looks backwards. Everything else
scores a posting against the judgment in config/; this reads what actually
happened to the applications that went out and asks whether that judgment is
holding up. The output is a markdown report a human reads and applies by
hand — the module has no write path to config/ at all, deliberately.

Three honesty rules shape every function here, and they exist because the
failure mode of a calibration report is not being wrong, it is being
CONFIDENT on data that cannot support it:

1. Nothing is dropped silently. An Outcome the mapping table never
   anticipated lands in the `other` bucket carrying the text the human
   typed. A Closed row with no archive behind it is counted in the header
   as an unjoined row, because a low join rate is itself the finding.

2. A contrast that could not produce a proposal is NAMED, with its actual
   Ns, in the suppressed section. A report that shows two proposals and
   says nothing about the two contrasts that failed the floor reads as
   though the data was cleaner than it was.

3. Nothing is generated from the clock. Every number in the report comes
   from the tracker text and the archive tree, so the same inputs produce
   the same bytes.

NOTE: this module and tools/calibrate.py share a basename. Imports of it
must stay fully qualified (`engine.loop.calibrate`), house precedent being
engine/draft/compile.py vs the `compile` builtin.
"""
from __future__ import annotations

from engine.loop.tracker_schema import parse_tracker

# Fixed bucket order. Every one is always a key in the returned dict, even
# when empty — a class that silently vanishes from the report reads as a
# class that never happened.
OUTCOME_BUCKETS = (
    "offer",
    "rejected-at-screen",
    "rejected-later",
    "timed-out",
    "no-response",
    "withdrawn",
    "other",
)

# The mapping table, in evaluation order — FIRST MATCH WINS, and the order is
# load-bearing rather than cosmetic:
#
# - "offer" leads, so "Offer declined" counts as an offer. They made one.
# - "screen" is checked before the generic "rejected", because "Rejected at
#   screen" carries both substrings and screening out is the opposite signal
#   from a late-stage rejection. Getting this backwards would quietly move
#   every screen rejection onto the interviewed side of every contrast.
# - "withdrew"/"withdrawn" sit above nothing in particular; no other entry
#   is a substring of them.
#
# Deliberately ABSENT: "declined" on its own. "Declined" is ambiguous about
# who declined whom, and a wrong guess here silently corrupts the interviewed
# group. It falls through to `other`, where a human can see it and decide.
OUTCOME_MAP = (
    ("offer", "offer"),
    ("screen", "rejected-at-screen"),
    ("timed out", "timed-out"),
    ("timeout", "timed-out"),
    ("no response", "no-response"),
    ("silence", "no-response"),
    ("ghost", "no-response"),
    ("withdrew", "withdrawn"),
    ("withdrawn", "withdrawn"),
    ("rejected", "rejected-later"),
    ("rejection", "rejected-later"),
)

_CLOSED_SECTION = "closed"


def classify_outcome(outcome: str) -> str:
    """The bucket one Outcome cell belongs to. Case-insensitive substring
    match against OUTCOME_MAP in order; anything unmatched (including an
    empty cell) is `other`, never a drop."""
    text = (outcome or "").strip().lower()
    if not text:
        return "other"
    for needle, bucket in OUTCOME_MAP:
        if needle in text:
            return bucket
    return "other"


def outcome_classes(tracker_text: str) -> dict:
    """Every Closed row bucketed by its Outcome cell.

    Returns a dict keyed by OUTCOME_BUCKETS in that exact order, values being
    lists of tracker_schema.Row in tracker order. A tracker with no Closed
    section yields the same keys with empty lists rather than a partial dict
    — the caller should never have to guess whether a missing key means "no
    rows" or "this module did not look".
    """
    classes = {bucket: [] for bucket in OUTCOME_BUCKETS}
    table = parse_tracker(tracker_text or "").get(_CLOSED_SECTION)
    if table is None:
        return classes
    for row in table.rows:
        classes[classify_outcome(row.get("Outcome"))].append(row)
    return classes
