"""Path calibration — which outreach gets replies, and whether a referral
changes the interview rate.

Same honesty rules as engine/loop/calibrate.py, reused rather than restated:
the same N floor and gap threshold, every group below the floor named with
its N, nothing read from the clock, nothing written. A send still waiting on
an answer is `pending` and sits out of every rate; `due` turns it into
`no_reply` after ten quiet business days, at which point it counts.
"""
from __future__ import annotations

from dataclasses import dataclass

from engine.loop.calibrate import (
    DEFAULT_MIN_N, MIN_GAP_POINTS, NEVER_EDITS_LINE, ContrastResult,
    ContrastSpec, _pct, closed_rows, group_joined, join_archives)
from engine.network.company import canonical
from engine.network.touches import REPLY_STATES

DIMENSIONS = (("path", "path"), ("hook", "hook"), ("register", "register"))

REFERRED = ContrastSpec(
    key="referred",
    present_label="a referral recorded for the company",
    absent_label="no referral recorded",
    config_file="weights.yaml",
    config_key="warm_path_pts (does not exist yet; adding it would be the change)",
    verb_when_interviewed="adding",
    verb_when_negative="not adding",
    bridge_when_interviewed="so a posting with a warm path ranks above one without",
    bridge_when_negative="because referred applications did not interview more",
)


@dataclass(frozen=True)
class Send:
    company: str
    person: str
    path: str
    hook: str
    register: str
    control: str
    outcome: str  # replied | no_reply | pending


def sends(touches, aliases) -> list:
    """One Send per (company, person) with an `asked` row. Dimensions come
    from the first ask; the outcome from the newest row."""
    first, last = {}, {}
    for index, t in enumerate(touches):
        if not t.person_slug:
            continue
        key = (canonical(t.company, aliases), t.person_slug)
        if t.state == "asked" and key not in first:
            first[key] = t
        rank = (t.date, index)
        if key not in last or rank >= last[key][0]:
            last[key] = (rank, t)
    out = []
    for key, ask in first.items():
        latest = last[key][1]
        if latest.state in REPLY_STATES:
            outcome = "replied"
        elif latest.state in ("no_reply", "left_company"):
            outcome = "no_reply"
        else:
            outcome = "pending"
        out.append(Send(ask.company, ask.person_slug, ask.path, ask.hook_level,
                        ask.register, ask.control, outcome))
    return out


def _resolved(items):
    return [s for s in items if s.outcome != "pending"]


def reply_lines(all_sends, min_n: int) -> list:
    """One line per value of each dimension: its reply rate, or "too few"
    with its N when it is under the floor. Never dropped."""
    lines = []
    resolved = _resolved(all_sends)
    for label, attr in DIMENSIONS:
        values = sorted({getattr(s, attr) for s in resolved if getattr(s, attr)})
        for value in values:
            group = [s for s in resolved if getattr(s, attr) == value]
            replied = sum(1 for s in group if s.outcome == "replied")
            if len(group) < min_n:
                lines.append(f"- {label}={value}: too few (N={len(group)}, "
                             f"floor {min_n})")
            else:
                lines.append(f"- {label}={value}: {replied} of {len(group)} replied "
                             f"({_pct(replied / len(group) * 100)}%)")
    return lines or ["- no resolved sends yet"]


def control_line(all_sends, min_n: int) -> str:
    """Matched register against the neutral control, for the paths that get
    one (recent_hire, cold_hm), excluding `unclear` labels."""
    pool = [s for s in _resolved(all_sends)
            if s.path in ("recent_hire", "cold_hm") and s.register != "unclear"]
    matched = [s for s in pool if s.control == "no"]
    control = [s for s in pool if s.control == "yes"]
    if len(matched) < min_n or len(control) < min_n:
        return (f"- matched register vs control: too few "
                f"(matched N={len(matched)}, control N={len(control)}, "
                f"floor {min_n})")
    m = sum(1 for s in matched if s.outcome == "replied") / len(matched) * 100
    c = sum(1 for s in control if s.outcome == "replied") / len(control) * 100
    verdict = "clears" if abs(m - c) >= MIN_GAP_POINTS else "below"
    return (f"- matched register vs control: {_pct(m)}% vs {_pct(c)}% "
            f"({_pct(abs(m - c))}-point gap, {verdict} the "
            f"{_pct(MIN_GAP_POINTS)}-point bar; matched N={len(matched)}, "
            f"control N={len(control)})")


def referral_result(joined, touches, aliases) -> ContrastResult:
    """Interview rate for applications at companies where a referral was
    recorded, against those without. Joined by canonical company name."""
    referred = {canonical(t.company, aliases) for t in touches
                if t.state == "referred"}
    interviewed, negative = group_joined(joined)

    def hit(app):
        return canonical(app.company, aliases) in referred

    return ContrastResult(
        spec=REFERRED,
        interviewed_hits=sum(1 for a in interviewed if hit(a)),
        interviewed_n=len(interviewed),
        negative_hits=sum(1 for a in negative if hit(a)),
        negative_n=len(negative))


def paths_report(tracker_text, archive_dir, touches, aliases,
                 min_n: int = DEFAULT_MIN_N) -> str:
    all_sends = sends(touches, aliases)
    pending = sum(1 for s in all_sends if s.outcome == "pending")
    lines = ["# Path calibration", "",
             f"Sends recorded: {len(all_sends)} ({pending} still pending, "
             "excluded from every rate).", "",
             "## Reply rates", ""]
    lines += reply_lines(all_sends, min_n)
    lines += ["", control_line(all_sends, min_n), "",
              "## Referral vs interview rate", ""]

    joined, _, _ = join_archives(closed_rows(tracker_text), archive_dir)
    result = referral_result(joined, touches, aliases)
    lines.append(result.contrast_line())
    i_n, n_n = result.underpowered_for
    if i_n < min_n or n_n < min_n:
        lines.append(f"- no proposal: too few (interviewed N={i_n}, "
                     f"negative N={n_n}, floor {min_n}).")
    elif result.gap < result.required_gap():
        lines.append(f"- no proposal: {_pct(result.gap)}-point gap is under the "
                     f"{_pct(result.required_gap())}-point bar at these Ns.")
    else:
        lines.append(f"- proposal: {result.suggestion()} — {result.evidence()}, "
                     f"{result.bridge()}.")
    lines += ["", NEVER_EDITS_LINE, ""]
    return "\n".join(lines)
