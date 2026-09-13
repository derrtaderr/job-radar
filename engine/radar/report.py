"""The day's delivery folder — one directory per run date holding queue.md and
a jd/ file for every posting the run touched.

The report is the whole product of a run: a ranked table a human reads, and
underneath it the kills, shown rather than swallowed, each quoting the line of
the posting that triggered it. Nothing here decides anything; it renders what
the pipeline decided so the decision can be checked in seconds.
"""
from __future__ import annotations


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
