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

from dataclasses import dataclass
from pathlib import Path

from engine.loop.archive import ArchiveError, read_outcome
from engine.loop.tracker_schema import parse_tracker
from engine.radar.tracker import _normalize_tracker_cell

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


# Same floor the radar's own tracker matching uses: below four characters a
# substring match degenerates into matching everything, so a two-letter cell
# must not be allowed to claim an archive.
_SOFT_MATCH_FLOOR = 4


@dataclass
class JoinedApplication:
    """One Closed tracker row paired with the archive directory behind it.
    `row` is the tracker_schema.Row (the outcome side); `archive` is the
    slug directory (the JD and posting side). Contrasts need both — the
    outcome comes from the tracker, every scored feature comes from the
    archive."""
    row: object
    archive: Path
    company: str
    role: str


def _soft_match(left: str, right: str) -> bool:
    """Normalized substring match in either direction, floored at four
    characters. The two sides are written by different authors and at
    different times — a tracker cell says "Harborlight (via referral)"
    where an archive says "Harborlight" — so exact equality would miss real
    joins and inflate the unjoined count into a false data-quality alarm."""
    a = _normalize_tracker_cell(left)
    b = _normalize_tracker_cell(right)
    if not a or not b or min(len(a), len(b)) < _SOFT_MATCH_FLOOR:
        return False
    return a in b or b in a


def _archive_identities(archive_dir: Path) -> list:
    """(slug_dir, company, role) for every archived application, in sorted
    slug order so the join never depends on filesystem listing order.

    An archive whose outcome.md is missing or malformed contributes its SLUG
    as both company and role rather than being skipped — the slug usually
    carries the same two facts, and a silently skipped archive would show up
    as a phantom unjoined row with no way to tell the two causes apart.
    """
    archive_dir = Path(archive_dir)
    if not archive_dir.is_dir():
        return []
    identities = []
    for slug_dir in sorted(p for p in archive_dir.iterdir() if p.is_dir()):
        try:
            meta = read_outcome(slug_dir)
            company = meta.get("company") or slug_dir.name
            role = meta.get("role") or slug_dir.name
        except (OSError, ArchiveError, KeyError, ValueError):
            company = role = slug_dir.name.replace("-", " ")
        identities.append((slug_dir, company, role))
    return identities


def join_archives(closed_rows, archive_dir) -> tuple:
    """Pair Closed tracker rows with the archived applications behind them.

    Returns `(joined, unjoined)` — a list of JoinedApplication and a list of
    the Rows that matched nothing. BOTH are returned and both are counted in
    the report header, because the join rate is a data-quality finding in its
    own right: a report built on four of twenty applications is saying
    something very different from one built on eighteen, and a function that
    returned only the joined side would hide exactly that difference.

    Matching needs company AND role to agree (soft-matched in either
    direction). Company alone is not enough — the same employer posting two
    roles is two applications, and attributing one posting's JD to the
    other's outcome is the quiet way to corrupt every contrast downstream.
    Each archive is consumed at most once, so a legitimate re-application to
    the same company and role (which the Closed section allows by design)
    cannot double-count the one archive behind it.
    """
    identities = _archive_identities(archive_dir)
    claimed = set()
    joined = []
    unjoined = []

    for row in closed_rows:
        company = row.get("Company") or ""
        role = row.get("Role") or ""
        match = None
        for idx, (slug_dir, arch_company, arch_role) in enumerate(identities):
            if idx in claimed:
                continue
            if _soft_match(company, arch_company) and _soft_match(role, arch_role):
                match = (idx, slug_dir, arch_company, arch_role)
                break
        if match is None:
            unjoined.append(row)
            continue
        idx, slug_dir, arch_company, arch_role = match
        claimed.add(idx)
        joined.append(JoinedApplication(
            row=row, archive=slug_dir, company=arch_company, role=arch_role))

    return joined, unjoined
