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


def day_paths(output_dir, day):
    """(day_dir, queue_path, jd_dir) for one run date.

    One folder per day, holding the queue and every JD it references, so acting
    on a queue is "open today's folder" instead of hunting across an output tree
    for the pieces of a single run.
    """
    day_dir = Path(output_dir) / str(day)
    return day_dir, day_dir / "queue.md", day_dir / "jd"


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


def _prior_cell(r: dict) -> str:
    """The verdict this posting was already judged under, e.g. `kill
    (bi-analytics)`, or empty.

    Its own column rather than a note buried in a list, because the miss this
    closes is a req the human had already killed by hand coming back as the top
    row. It has to be legible at the same glance they rank everything else at.
    """
    prior = r.get("prior")
    if not prior:
        return ""
    reason = f" ({prior.reason})" if prior.reason else ""
    return _esc(f"{prior.verdict}{reason}")


def _flag_names(r: dict) -> list:
    """The non-kill flags on a row, as short tokens for the table. The quoted
    evidence behind each one lives in the "Flagged, not killed" section — a
    table cell is the wrong place for a ±40-char quote, and dropping the quote
    to fit would break this repo's floor that every flag is checkable."""
    names = []
    if r.get("repost_of"):
        names.append(f"possible repost of {r['repost_of']}")
    names += [name for name, _ in r.get("notes") or ()]
    return names


def _render_survivor_row(r: dict) -> str:
    return (f"| {r['score']} | {_esc(r['title'])} | {_esc(r['company'])} | {_comp(r)} "
            f"| {r.get('date_posted') or ''} | {_esc(r.get('location') or '')} "
            f"| {_prior_cell(r)} | {_esc('; '.join(_flag_names(r)))} "
            f"| {_jd_link(r)} | {r.get('job_url') or ''} |")


def _render_killed_line(r: dict) -> str:
    """A kill is shown, never swallowed: the posting struck through, every rule
    that fired, and the quoted line of the posting that matched it. A prior
    hand-verdict rides along — on a killed row it says the rule is doing what
    the human wanted, which is the one thing that tells you not to loosen it."""
    flags = "; ".join(f'**{n}**: "{ev}"' for n, ev in r["flags"])
    jd = _jd_link(r)
    tail = f" — {jd}" if jd else ""
    prior = _prior_cell(r)
    prior_note = f" — prior: {prior}" if prior else ""
    extra = _flag_names(r)
    extra_note = f" — {'; '.join(extra)}" if extra else ""
    return (f"- ~~{_esc(r['title'])} @ {_esc(r['company'])}~~ — {flags}"
            f"{prior_note}{extra_note} "
            f"— {r.get('job_url') or ''}{tail}")


def _flagged_rows(survivors, killed) -> list:
    """Every row carrying something non-kill worth quoting."""
    return [r for r in list(survivors) + list(killed)
            if r.get("prior") or r.get("repost_of") or r.get("notes")]


def _render_flagged_line(r: dict) -> str:
    parts = []
    prior = r.get("prior")
    if prior:
        reason = f" ({prior.reason})" if prior.reason else ""
        parts.append(f"**prior verdict**: {prior.verdict}{reason} on {prior.date}")
    if r.get("repost_of"):
        parts.append(f"**possible repost of** {r['repost_of']}")
    parts += [f'**{name}**: "{ev}"' for name, ev in r.get("notes") or ()]
    return f"- {_esc(r.get('title'))} @ {_esc(r.get('company'))} — " + "; ".join(parts)


def _render_body(survivors, killed) -> str:
    """The survivors table plus the killed list, without frontmatter. Shared by
    a fresh write and a same-day append so both paths render identically."""
    lines = [
        # Leading blank line: markdown needs one before a table, or the
        # paragraph above swallows it and the queue renders as a wall of pipes.
        "",
        "| Score | Role | Company | Comp | Posted | Where | Prior | Flags | JD | Link |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in sorted(survivors, key=lambda r: -r["score"]):
        lines.append(_render_survivor_row(r))
    if killed:
        lines += ["", "## Killed by rule (overrule by hand if the flag is wrong)", ""]
        for r in killed:
            lines.append(_render_killed_line(r))
    flagged = _flagged_rows(survivors, killed)
    if flagged:
        lines += ["", "## Flagged, not killed (the evidence behind the Flags column)", ""]
        for r in flagged:
            lines.append(_render_flagged_line(r))
    return "\n".join(lines)


def _judged_note(survivors, killed) -> str:
    """A sentence counting the rows you already judged, or nothing.

    Only when there are some. A standing "0 already judged" on every quiet day
    would train the eye to skip the line, which is the one line that matters on
    the day it is not zero.
    """
    judged = [r for r in list(survivors) + list(killed) if r.get("prior")]
    if not judged:
        return ""
    return (f" {len(judged)} already judged — your prior verdict is in the Prior "
            "column, never a reason a posting was hidden.")


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
        "(shown below, never silently)."
        + _judged_note(survivors, killed),
        "",
    ]
    return "\n".join(header) + _render_body(survivors, killed) + "\n"


def write_report(path, survivors, killed, day) -> bool:
    """Write the day's queue. Returns True if anything was written.

    A second run on the same day APPENDS rather than overwrites. By the time it
    runs you may already have acted on the first run's queue, and silently
    replacing it would destroy the record of what you were working from.
    """
    report = render_report(survivors, killed, day)
    if not report:
        return False
    path = Path(path)
    if path.exists():
        with path.open("a") as f:
            f.write("\n## Later run (same day)\n\n"
                    + _render_body(survivors, killed) + "\n")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report)
    return True
