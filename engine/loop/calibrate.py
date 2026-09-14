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


def closed_rows(tracker_text: str) -> list:
    """Every Closed row in TRACKER order.

    The join consumes each archive once, so the order rows arrive in decides
    who wins a contested archive. Bucket order would let an `offer` row from
    the bottom of the file claim an archive ahead of a `no-response` row
    above it, quietly biasing the interviewed side of every contrast upward.
    File order has no such lean.
    """
    table = parse_tracker(tracker_text or "").get(_CLOSED_SECTION)
    return list(table.rows) if table is not None else []


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
class AmbiguousMatch:
    """A Closed row that soft-matched more than one archive and was therefore
    joined to NONE of them. `candidates` are the slug names it could not
    choose between, so the report can name them and a human can rename one
    side or correct the tracker cell."""
    row: object
    candidates: list


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
        # The fallback identity is the slug with hyphens turned back into
        # spaces, and it has to be spelled the same way on BOTH branches — a
        # raw "cobalt-grid-data-engineer" can never substring-match a tracker
        # cell reading "Cobalt Grid", so a fallback left hyphenated is one
        # that never fires while looking handled.
        slug_identity = slug_dir.name.replace("-", " ")
        try:
            meta = read_outcome(slug_dir)
            company = meta.get("company") or slug_identity
            role = meta.get("role") or slug_identity
        except (OSError, ArchiveError, KeyError, ValueError):
            company = role = slug_identity
        identities.append((slug_dir, company, role))
    return identities


def join_archives(closed_rows, archive_dir) -> tuple:
    """Pair Closed tracker rows with the archived applications behind them.

    Returns `(joined, unjoined, ambiguous)`. `unjoined` is the complete
    complement of `joined` — every row that ended up attached to nothing,
    ambiguous ones included — so `len(joined) + len(unjoined)` always equals
    the number of rows in. `ambiguous` is the subset of those that failed
    because too MANY archives matched, carried separately only so the report
    can name them and their candidates.

    All three are returned because the join rate is a data-quality finding in
    its own right: a report built on four of twenty applications says
    something very different from one built on eighteen.

    ## Why exact equality has to run first, across ALL candidates

    Substring matching in either direction is what lets "Harborlight (via
    referral)" find "Harborlight". It is also what silently swaps two
    applications: "Data Engineer" is a substring of "Analytics Data
    Engineer", so a first-match-wins substring scan over one company's two
    archives hands each row the other's JD — with unjoined empty and a 100%
    join rate, which reads as a clean run while every contrast downstream is
    scored against the wrong postings. There is no symptom.

    So the order is: normalized exact equality on company AND role, checked
    against every unclaimed archive, wins outright. Only when nothing matches
    exactly does substring run, and only when it finds EXACTLY ONE candidate
    is that candidate used. Two or more is an ambiguity, and a guess there is
    precisely the bug above, so the row joins nothing and says which archives
    it could not choose between.

    Company alone is never enough: one employer posting two roles is two
    applications. Each archive is consumed at most once, so a legitimate
    re-application to the same company and role (which the Closed section
    allows by design) cannot double-count the one archive behind it. Rows are
    processed in the order given, which the caller keeps as TRACKER order.
    """
    identities = _archive_identities(archive_dir)
    claimed = set()
    joined, unjoined, ambiguous = [], [], []

    for row in closed_rows:
        company = row.get("Company") or ""
        role = row.get("Role") or ""
        available = [(idx, slug_dir, arch_company, arch_role)
                     for idx, (slug_dir, arch_company, arch_role)
                     in enumerate(identities) if idx not in claimed]

        exact = [c for c in available
                 if _normalize_tracker_cell(company) == _normalize_tracker_cell(c[2])
                 and _normalize_tracker_cell(role) == _normalize_tracker_cell(c[3])]
        if exact:
            # More than one exact match means genuine duplicate archives for
            # the same company and role; taking the first in slug order is
            # deterministic, and the next identical row takes the next one.
            candidates = exact[:1]
        else:
            candidates = [c for c in available
                          if _soft_match(company, c[2]) and _soft_match(role, c[3])]

        if len(candidates) == 1:
            idx, slug_dir, arch_company, arch_role = candidates[0]
            claimed.add(idx)
            joined.append(JoinedApplication(
                row=row, archive=slug_dir, company=arch_company, role=arch_role))
            continue

        unjoined.append(row)
        if len(candidates) > 1:
            ambiguous.append(AmbiguousMatch(
                row=row, candidates=[c[1].name for c in candidates]))

    return joined, unjoined, ambiguous


# --- contrasts --------------------------------------------------------------

# How outcome classes fold into the two sides of every contrast.
#
# "Interviewed" is offer + rejected-later: both got past the screen, which is
# the thing the radar's scoring is actually trying to predict. A late-stage
# rejection is evidence the posting was worth applying to even though the
# application failed, and filing it with the screen-outs would wash out the
# only signal here.
#
# "Negative" is no-response + rejected-at-screen + timed-out: the posting
# never engaged. Silence and a screen rejection differ in politeness, not in
# what they say about the posting.
#
# withdrawn and other are in NEITHER, and that is deliberate rather than an
# oversight. A withdrawal is a fact about the applicant's decision, not about
# the posting, so scoring rules cannot be tuned against it; `other` is by
# definition a class nobody has interpreted yet. Both are counted in the
# report header so their exclusion is visible.
INTERVIEWED_CLASSES = ("offer", "rejected-later")
NEGATIVE_CLASSES = ("no-response", "rejected-at-screen", "timed-out")

EXCLUDED_FROM_CONTRASTS = ("withdrawn", "other")

INTERVIEWED_LABEL = "interviewed"
NEGATIVE_LABEL = "negative-outcome"

# A proposal needs BOTH a floor on N and a floor on effect size. Either one
# alone produces confident nonsense: a 100-point gap between two applications
# and one, or a 2-point gap across a hundred.
DEFAULT_MIN_N = 5
MIN_GAP_POINTS = 20.0

NEVER_EDITS_LINE = (
    "This report never edits config. Every proposal above is a suggestion a "
    "human applies by hand, after checking it against what they remember of "
    "the applications behind it.")


@dataclass(frozen=True)
class ContrastSpec:
    """One engine-scored feature, and what a difference in it would imply.

    `present_label` and `absent_label` are both spelled out because the
    interesting framing depends on which way the data falls — "unlisted comp"
    is the readable statement when comp is missing from the losers, "comp
    listed" when it is present in the winners. `raise_key`/`lower_key` name
    the config the human would edit in either direction.
    """
    key: str
    present_label: str
    absent_label: str
    config_file: str
    config_key: str
    # Verb to use when the feature is MORE common among the interviewed
    # group, and when it is more common among the negative group.
    verb_when_interviewed: str
    verb_when_negative: str


CONTRASTS = (
    ContrastSpec(
        key="comp",
        present_label="comp listed in the JD",
        absent_label="unlisted comp",
        config_file="weights.yaml",
        config_key="unlisted_comp_pts",
        # unlisted_comp_pts is the score an unlisted posting receives. If
        # listed comp tracks with interviews, unlisted postings deserve less
        # of it; if the reverse, the current penalty is too harsh.
        verb_when_interviewed="lowering",
        verb_when_negative="raising",
    ),
    ContrastSpec(
        key="remote",
        present_label="remote language in the JD",
        absent_label="no remote language in the JD",
        config_file="weights.yaml",
        config_key="remote_pts",
        verb_when_interviewed="raising",
        verb_when_negative="lowering",
    ),
    ContrastSpec(
        key="title_tier",
        present_label="a title-tier hit on the role title",
        absent_label="no title-tier hit on the role title",
        config_file="weights.yaml",
        config_key="title_tiers",
        verb_when_interviewed="raising",
        verb_when_negative="lowering",
    ),
    ContrastSpec(
        key="kill_near_miss",
        present_label="kill-rule language in the JD",
        absent_label="no kill-rule language in the JD",
        config_file="rules.yaml",
        config_key="rules",
        # A kill rule matching a JD that was applied to anyway is a NEAR MISS:
        # the rule did not fire at scrape time (the archived JD text is often
        # fuller than what the scraper saw) but the language was there. If
        # those applications went nowhere, the rules are reading real signal
        # and should be tightened; if they interviewed, the rules are too
        # aggressive and should be loosened.
        verb_when_interviewed="loosening",
        verb_when_negative="tightening",
    ),
)


def _jd_text(application: JoinedApplication) -> str:
    """The archived JD, or empty string when the archive has none. An empty
    JD reads as "none of the text features present" rather than raising —
    every feature here is a presence check, and absence is the honest answer
    for a posting whose text was never kept."""
    path = Path(application.archive) / "jd.md"
    try:
        return path.read_text()
    except OSError:
        return ""


def application_features(application: JoinedApplication, cfg) -> dict:
    """The engine-scored features of one archived application, as booleans
    keyed by ContrastSpec.key. Every detector is imported from the radar
    rather than reimplemented, so calibration measures what the radar
    actually does and not a second opinion about it."""
    from engine.radar.rules_engine import body_stated_max, jd_says_remote

    text = _jd_text(application)
    return {
        "comp": body_stated_max(text) is not None,
        "remote": jd_says_remote(text) is not None,
        "title_tier": any(pattern.search(application.role or "")
                          for pattern, _points in cfg.title_tiers),
        "kill_near_miss": any(rule.pattern.search(text)
                              for rule in cfg.kill_rules),
    }


def _rate(hits: int, total: int) -> float:
    return (hits / total * 100.0) if total else 0.0


def _pct(value: float) -> int:
    return int(round(value))


@dataclass
class ContrastResult:
    spec: ContrastSpec
    interviewed_hits: int
    interviewed_n: int
    negative_hits: int
    negative_n: int

    @property
    def interviewed_rate(self) -> float:
        return _rate(self.interviewed_hits, self.interviewed_n)

    @property
    def negative_rate(self) -> float:
        return _rate(self.negative_hits, self.negative_n)

    @property
    def gap(self) -> float:
        """Absolute difference in percentage points, computed from the RAW
        rates rather than the rounded display percentages — 67% vs 71% is a
        5-point gap, and rounding first would report 4."""
        return abs(self.interviewed_rate - self.negative_rate)

    def noise_floor(self) -> float:
        """The gap that two applications of movement would produce on the
        SMALLER side, in percentage points.

        A flat threshold alone is not a floor at small N. At min_n=5 one
        application is worth exactly 20 points, so a 5-of-5 versus 4-of-5
        split cleared a 20-point bar and proposed a config change off a
        single person's hiring decision. Two applications is the minimum
        that can be called a pattern rather than an anecdote, and the
        smaller side sets the bar because one application moves its rate
        further.
        """
        smaller = min(self.interviewed_n, self.negative_n)
        if smaller <= 0:
            return float("inf")
        return 2 * 100.0 / smaller

    def required_gap(self) -> float:
        """The gap this contrast must actually clear — a max(), never a
        swap. At large N two applications is a few points and the flat
        threshold binds; at small N the noise floor does."""
        return max(MIN_GAP_POINTS, self.noise_floor())

    @property
    def underpowered_for(self):
        """(interviewed_n, negative_n) when either side is below the floor —
        checked by the caller, which knows the floor."""
        return self.interviewed_n, self.negative_n

    def evidence(self) -> str:
        """The strongest TRUE statement this contrast supports, leading with
        whichever of the four (side, polarity) cells has the highest rate.

        Both polarities are honest descriptions of the same two counts, so
        the choice is presentational — but it is not arbitrary. Leading with
        the highest cell puts the most legible version of the finding first
        ("6 of 7 negative-outcome applications had unlisted comp" rather than
        "1 of 7 had comp listed"), and fixing the rule keeps the report
        byte-reproducible. Ties break toward the earlier cell in this order.
        """
        cells = (
            (self.interviewed_rate, INTERVIEWED_LABEL, NEGATIVE_LABEL,
             self.spec.present_label, self.interviewed_hits, self.interviewed_n,
             self.negative_hits, self.negative_n),
            (100.0 - self.interviewed_rate, INTERVIEWED_LABEL, NEGATIVE_LABEL,
             self.spec.absent_label,
             self.interviewed_n - self.interviewed_hits, self.interviewed_n,
             self.negative_n - self.negative_hits, self.negative_n),
            (self.negative_rate, NEGATIVE_LABEL, INTERVIEWED_LABEL,
             self.spec.present_label, self.negative_hits, self.negative_n,
             self.interviewed_hits, self.interviewed_n),
            (100.0 - self.negative_rate, NEGATIVE_LABEL, INTERVIEWED_LABEL,
             self.spec.absent_label,
             self.negative_n - self.negative_hits, self.negative_n,
             self.interviewed_n - self.interviewed_hits, self.interviewed_n),
        )
        _rate_, lead, other, label, lead_hits, lead_n, other_hits, other_n = max(
            cells, key=lambda c: c[0])
        return (f"{lead_hits} of {lead_n} {lead} applications had {label}, "
                f"vs {other_hits} of {other_n} {other}")

    def suggestion(self) -> str:
        verb = (self.spec.verb_when_interviewed
                if self.interviewed_rate >= self.negative_rate
                else self.spec.verb_when_negative)
        return (f"`{self.spec.config_file}`: consider {verb} "
                f"`{self.spec.config_key}`")

    def contrast_line(self) -> str:
        return (f"- {self.spec.present_label}: "
                f"{self.interviewed_hits} of {self.interviewed_n} "
                f"{INTERVIEWED_LABEL} ({_pct(self.interviewed_rate)}%) vs "
                f"{self.negative_hits} of {self.negative_n} "
                f"{NEGATIVE_LABEL} ({_pct(self.negative_rate)}%) "
                f"— {_pct(self.gap)}-point gap")


def group_joined(joined) -> tuple:
    """Joined applications split into (interviewed, negative). The one place
    the grouping is computed, so the header and the contrasts can never
    disagree about how many applications are on each side."""
    interviewed, negative = [], []
    for application in joined:
        bucket = classify_outcome(application.row.get("Outcome"))
        if bucket in INTERVIEWED_CLASSES:
            interviewed.append(application)
        elif bucket in NEGATIVE_CLASSES:
            negative.append(application)
    return interviewed, negative


def contrast_results(joined, cfg) -> list:
    """One ContrastResult per CONTRASTS entry, in that fixed order."""
    interviewed_apps, negative_apps = group_joined(joined)
    interviewed = [application_features(a, cfg) for a in interviewed_apps]
    negative = [application_features(a, cfg) for a in negative_apps]

    return [
        ContrastResult(
            spec=spec,
            interviewed_hits=sum(1 for f in interviewed if f[spec.key]),
            interviewed_n=len(interviewed),
            negative_hits=sum(1 for f in negative if f[spec.key]),
            negative_n=len(negative),
        )
        for spec in CONTRASTS
    ]


def _summary_lines(classes: dict, joined, unjoined, ambiguous, min_n: int) -> list:
    total = sum(len(rows) for rows in classes.values())
    n_joined = len(joined)
    join_pct = _pct(_rate(n_joined, total))
    # Counted off the joined population itself, never read from a contrast
    # result. A contrast's N is a derived number that a future contrast with
    # its own determinability rule could legitimately shrink, at which point
    # the header would be quietly describing one contrast instead of the
    # group it claims to describe.
    interviewed, negative = group_joined(joined)
    interviewed_n, negative_n = len(interviewed), len(negative)

    lines = [
        "## Summary",
        "",
        f"Closed applications: {total}",
        f"Joined to an archive: {n_joined} ({join_pct}%)",
        f"Unjoined (no archive match): {len(unjoined)}",
    ]
    if ambiguous:
        # Named, not just counted. An ambiguity is fixable in about a minute
        # once a human can see WHICH two archives collided; as a bare number
        # it is an unactionable complaint.
        lines.append(
            f"Ambiguous (more than one archive matched, so joined to none; "
            f"counted in unjoined above): {len(ambiguous)}")
        for match in ambiguous:
            company = (match.row.get("Company") or "").strip()
            role = (match.row.get("Role") or "").strip()
            lines.append(
                f"  - {company} / {role}: "
                f"{', '.join(sorted(match.candidates))}")
    lines += ["", "Outcome classes:"]
    for bucket in OUTCOME_BUCKETS:
        lines.append(f"- {bucket}: {len(classes[bucket])}")
        if bucket == "other" and classes[bucket]:
            # Verbatim, and counted. An Outcome nobody anticipated is a
            # prompt to extend the mapping table, which it cannot be if the
            # report only ever shows a number.
            verbatim = {}
            for row in classes[bucket]:
                text = (row.get("Outcome") or "").strip() or "(blank)"
                verbatim[text] = verbatim.get(text, 0) + 1
            for text, count in sorted(verbatim.items(),
                                      key=lambda kv: (-kv[1], kv[0])):
                lines.append(f'  - "{text}": {count}')

    lines += [
        "",
        f'Contrast groups: "{INTERVIEWED_LABEL}" is '
        f"{' + '.join(INTERVIEWED_CLASSES)} (they got past the screen), "
        f"{interviewed_n} joined. "
        f'"{NEGATIVE_LABEL}" is {" + ".join(NEGATIVE_CLASSES)}, '
        f"{negative_n} joined.",
        f"{' and '.join(EXCLUDED_FROM_CONTRASTS)} are counted above and "
        "excluded from every contrast — a withdrawal is a fact about the "
        "applicant, not the posting, and `other` is a class nobody has "
        "interpreted yet.",
        "",
        f"Proposal floor: both sides need N >= {min_n}, and the rate gap must "
        f"be at least {_pct(MIN_GAP_POINTS)} points and at least two "
        f"applications of movement at these Ns.",
        "",
        "Contrasts use the CURRENT config; rules/weights edited since an "
        "application was decided will show as near-misses.",
    ]
    return lines


def calibration_report(tracker_text: str, archive_dir, cfg,
                       min_n: int = DEFAULT_MIN_N) -> str:
    """A markdown calibration report over one season of resolved outcomes.

    Sections, in this order and always all four: Summary (totals, class
    counts, join rate, the contrast grouping, the floor), Outcome contrasts
    (joined applications only), Proposals, Suppressed proposals. Every
    contrast lands in exactly one of the last two, which is what makes the
    suppressed section worth reading — a contrast that appeared in neither
    would be a silent drop wearing a report's clothes.

    Nothing here writes anything. `cfg` is read for its title_tiers and
    kill_rules and is never modified.
    """
    classes = outcome_classes(tracker_text)
    rows = closed_rows(tracker_text)
    joined, unjoined, ambiguous = join_archives(rows, archive_dir)
    results = contrast_results(joined, cfg)

    lines = ["# Calibration report", ""]
    lines += _summary_lines(classes, joined, unjoined, ambiguous, min_n)

    lines += [
        "",
        "## Outcome contrasts",
        "",
        f"Joined applications only ({len(joined)} of "
        f"{len(rows)}). Each line reads: feature present among "
        f"{INTERVIEWED_LABEL} vs among {NEGATIVE_LABEL}.",
        "",
    ]
    lines += [result.contrast_line() for result in results]

    proposals, suppressed = [], []
    for result in results:
        interviewed_n, negative_n = result.underpowered_for
        if interviewed_n < min_n or negative_n < min_n:
            suppressed.append(
                f"- {result.spec.present_label}: insufficient data "
                f"({INTERVIEWED_LABEL} N={interviewed_n}, "
                f"{NEGATIVE_LABEL} N={negative_n}; floor N={min_n}).")
        elif result.gap < MIN_GAP_POINTS:
            suppressed.append(
                f"- {result.spec.present_label}: gap below threshold "
                f"({_pct(result.gap)}-point gap vs the "
                f"{_pct(MIN_GAP_POINTS)}-point threshold; "
                f"{INTERVIEWED_LABEL} N={interviewed_n}, "
                f"{NEGATIVE_LABEL} N={negative_n}, floor N={min_n}).")
        elif result.gap < result.noise_floor():
            # Named for what it is. "Below threshold" would be misleading
            # here — the gap DID clear the stated threshold, and what stopped
            # it is that at these Ns the whole gap is one application moving.
            smaller = min(interviewed_n, negative_n)
            suppressed.append(
                f"- {result.spec.present_label}: gap within one-application "
                f"noise at these Ns ({_pct(result.gap)}-point gap vs a "
                f"{_pct(result.noise_floor())}-point floor, which is two "
                f"applications at N={smaller}; "
                f"{INTERVIEWED_LABEL} N={interviewed_n}, "
                f"{NEGATIVE_LABEL} N={negative_n}, floor N={min_n}).")
        else:
            proposals.append(
                f"- {result.suggestion()} — {result.evidence()} "
                f"({_pct(result.gap)}-point gap vs a "
                f"{_pct(result.required_gap())}-point bar at these Ns, "
                f"floor N={min_n}).")

    lines += ["", "## Proposals", ""]
    if proposals:
        lines.append(
            f"{len(proposals)} of {len(results)} contrasts cleared the floor.")
        lines.append("")
        lines += proposals
    else:
        lines.append(
            f"No proposal cleared the floor. All {len(results)} contrasts are "
            "named below with the Ns that stopped them.")

    lines += ["", "## Suppressed proposals", ""]
    if suppressed:
        lines.append(
            f"{len(suppressed)} of {len(results)} contrasts produced no "
            "proposal. Every one is named here with its actual Ns, so the "
            "report cannot read as more confident than its data.")
        lines.append("")
        lines += suppressed
    else:
        lines.append("None. Every contrast cleared the floor.")

    lines += ["", NEVER_EDITS_LINE, ""]
    return "\n".join(lines)
