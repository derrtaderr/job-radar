"""The pipeline — raw scraped rows in, a ranked queue and a visible kill list out.

This is the one place the run's decisions are made, and it is deliberately a
pure function: rows, prior state, config, and the tracker set go in; survivors,
kills, and the NEW state come back. Nothing is read from or written to disk
here, which is what makes a whole run's behavior testable in a millisecond and
keeps a broken scrape from ever corrupting the seen-job memory.

Order matters and is not arbitrary. Cheap, certain suppressions (already seen,
duplicate URL, excluded employer, already in play) run before the expensive,
fallible ones (title filter, kill rules), so a row that should never have been
considered never gets scored, and never gets recorded as seen.
"""
from __future__ import annotations

from engine.radar.rules_engine import kill_flags, score, title_passes
from engine.radar.tracker import tracker_suppresses


def excluded(company, exclusions) -> bool:
    """Case-insensitive substring match against the never-surface list. Substring
    rather than exact, because "Northwind Analytics" and "Northwind Analytics,
    Inc." are the same employer and nobody should have to list both."""
    c = (company or "").lower()
    return any(x in c for x in exclusions)


def pipeline(raw_rows, state, cfg, tracker_set, today):
    """Returns (survivors, killed, new_state).

    Survivors are sorted best-first. Killed rows carry the flags that killed
    them, so the report can show the kill and quote its evidence rather than
    swallowing the posting. Both carry `jid`, the id their JD file is named
    after — kills included, so a suspected false kill is readable off disk.

    Only rows this run actually judged are added to state. A row suppressed by
    the tracker or the exclusion list is NOT recorded, so removing a company
    from either one lets its postings surface again instead of being silently
    remembered as already seen.
    """
    survivors, killed, new_state = [], [], dict(state)
    seen_urls, seen_pairs = set(), set()

    for r in raw_rows:
        jid = str(r.get("id") or r.get("job_url"))
        url = r.get("job_url")
        if jid in state or (url and url in seen_urls):
            continue
        if excluded(r.get("company"), cfg.exclusions):
            continue
        if tracker_suppresses(r.get("company"), tracker_set):
            continue
        if not title_passes(r.get("title"), cfg):
            continue
        # The same posting listed under two cities arrives as two ids with two
        # URLs. One company+title pair gets one queue slot per run.
        pair = ((r.get("company") or "").lower(), (r.get("title") or "").lower())
        if pair in seen_pairs:
            continue

        seen_pairs.add(pair)
        if url:
            seen_urls.add(url)
        new_state[jid] = str(today)

        flags = kill_flags(r, cfg)
        if flags:
            killed.append(dict(r, flags=flags, jid=jid))
        else:
            survivors.append(dict(r, score=score(r, today, cfg), jid=jid))

    survivors.sort(key=lambda r: -r["score"])
    return survivors, killed, new_state
