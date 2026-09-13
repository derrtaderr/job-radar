"""The day's delivery folder — one directory per run date holding queue.md and
a jd/ file for every posting the run touched.

The report is the whole product of a run: a ranked table a human reads, and
underneath it the kills, shown rather than swallowed, each quoting the line of
the posting that triggered it. Nothing here decides anything; it renders what
the pipeline decided so the decision can be checked in seconds.
"""
from __future__ import annotations

import re
from pathlib import Path


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


def _jd_filename(jid) -> str:
    """The filename a row's JD is stored under. `jid` falls back to the job URL
    when a row has no id, so slashes and colons have to be sanitized before they
    reach the filesystem. Shared by write_jds and the renderers, so the link and
    the file can never disagree."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(jid)) + ".md"


def _jd_link(r: dict) -> str:
    """Relative link to the row's local JD file, or '' when none was written.
    No description means no file, and a dead link is worse than no link."""
    if r.get("description") and r.get("jid"):
        return f"[jd](jd/{_jd_filename(r['jid'])})"
    return ""


def write_jds(jd_dir, survivors, killed, day) -> int:
    """Persist the full JD text the scrape already fetched — survivors AND
    kills. Reviewing the queue then reads local files instead of re-fetching
    postings, and checking a suspected false kill costs nothing. Returns the
    number of files written.
    """
    jd_dir = Path(jd_dir)
    written = 0
    for r in list(survivors) + list(killed):
        desc = r.get("description")
        if not desc or not r.get("jid"):
            continue
        jd_dir.mkdir(parents=True, exist_ok=True)
        killed_line = ""
        if r.get("flags"):
            evidence = "; ".join(f'**{n}**: "{ev}"' for n, ev in r["flags"])
            killed_line = f"\nKilled by: {evidence}\n"
        (jd_dir / _jd_filename(r["jid"])).write_text(
            "---\n"
            f"name: JD {r['jid']} — {r.get('company') or ''} — {r.get('title') or ''}\n"
            f"captured: {day}\n"
            f"source: {r.get('job_url') or ''}\n"
            "---\n\n"
            f"# {r.get('title') or ''} @ {r.get('company') or ''}\n\n"
            f"{_comp(r)} | posted {r.get('date_posted') or '?'} "
            f"| {r.get('location') or 'location unlisted'}\n"
            f"{killed_line}\n"
            f"{desc}\n")
        written += 1
    return written


def _render_survivor_row(r: dict) -> str:
    return (f"| {r['score']} | {_esc(r['title'])} | {_esc(r['company'])} | {_comp(r)} "
            f"| {r.get('date_posted') or ''} | {_esc(r.get('location') or '')} "
            f"| {_jd_link(r)} | {r.get('job_url') or ''} |")


def _render_killed_line(r: dict) -> str:
    """A kill is shown, never swallowed: the posting struck through, every rule
    that fired, and the quoted line of the posting that matched it."""
    flags = "; ".join(f'**{n}**: "{ev}"' for n, ev in r["flags"])
    jd = _jd_link(r)
    tail = f" — {jd}" if jd else ""
    return (f"- ~~{_esc(r['title'])} @ {_esc(r['company'])}~~ — {flags} "
            f"— {r.get('job_url') or ''}{tail}")


def _render_body(survivors, killed) -> str:
    """The survivors table plus the killed list, without frontmatter. Shared by
    a fresh write and a same-day append so both paths render identically."""
    lines = [
        "| Score | Role | Company | Comp | Posted | Where | JD | Link |",
        "|---|---|---|---|---|---|---|---|",
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
