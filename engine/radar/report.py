"""The day's delivery folder — one directory per run date holding queue.md and
a jd/ file for every posting the run touched.

The report is the whole product of a run: a ranked table a human reads, and
underneath it the kills, shown rather than swallowed, each quoting the line of
the posting that triggered it. Nothing here decides anything; it renders what
the pipeline decided so the decision can be checked in seconds.
"""
from __future__ import annotations


def _esc(s) -> str:
    """Escape '|' so a title, company, or location containing a pipe can't
    silently break the queue table's columns."""
    return str(s or "").replace("|", "\\|")


def _fmt_amount(x) -> str:
    """Scraped amounts arrive as floats. Drop a trailing ".0" so an hourly rate
    renders as "40" rather than "40.0"; keep a real fraction."""
    x = float(x)
    return str(int(x)) if x == int(x) else str(x)


def _comp(row: dict) -> str:
    """Compensation, human-sized.

    Yearly amounts collapse to thousands ("$150-190K") because that is how a
    person reads a salary band. Anything NOT yearly keeps its interval in the
    output, so an hourly rate can never be mistaken for a salary — rendering
    "$40-60K" for $40/hour would be a lie the reader has no way to catch.
    """
    lo, hi = row.get("min_amount"), row.get("max_amount")
    interval = row.get("interval")

    if interval and str(interval).lower() != "yearly":
        if lo and hi:
            return f"{_fmt_amount(lo)}-{_fmt_amount(hi)} {interval}"
        bound = hi or lo
        return f"{_fmt_amount(bound)} {interval}" if bound else "unlisted"

    if hi:
        if lo:
            return f"${int(float(lo) / 1000)}-{int(float(hi) / 1000)}K"
        return f"to ${int(float(hi) / 1000)}K"
    if lo:
        return f"from ${int(float(lo) / 1000)}K"
    return "unlisted"


def _render_survivor_row(r: dict) -> str:
    return (f"| {r['score']} | {_esc(r['title'])} | {_esc(r['company'])} | {_comp(r)} "
            f"| {r.get('date_posted') or ''} | {_esc(r.get('location') or '')} "
            f"| {r.get('job_url') or ''} |")


def _render_killed_line(r: dict) -> str:
    """A kill is shown, never swallowed: the posting struck through, every rule
    that fired, and the quoted line of the posting that matched it."""
    flags = "; ".join(f'**{n}**: "{ev}"' for n, ev in r["flags"])
    return (f"- ~~{_esc(r['title'])} @ {_esc(r['company'])}~~ — {flags} "
            f"— {r.get('job_url') or ''}")


def _render_body(survivors, killed) -> str:
    """The survivors table plus the killed list, without frontmatter. Shared by
    a fresh write and a same-day append so both paths render identically."""
    lines = [
        "| Score | Role | Company | Comp | Posted | Where | Link |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in sorted(survivors, key=lambda r: -r["score"]):
        lines.append(_render_survivor_row(r))
    if killed:
        lines += ["", "## Killed by rule (overrule by hand if the flag is wrong)", ""]
        for r in killed:
            lines.append(_render_killed_line(r))
    return "\n".join(lines)


def render_report(survivors, killed, day):
    """The day's queue as markdown, or None when the run produced nothing.

    None rather than an empty document is deliberate: a queue.md with no rows
    looks like a finished run that genuinely found nothing, which is the one
    thing a broken run also looks like.
    """
    if not survivors and not killed:
        return None
    header = [
        "---",
        f"name: Job radar {day}",
        "read_by: your daily review session",
        "---",
        "",
        f"# Job radar — {day}",
        "",
        f"{len(survivors)} in the queue, {len(killed)} killed by rule "
        "(shown below, never silently).",
        "",
    ]
    return "\n".join(header) + _render_body(survivors, killed) + "\n"
