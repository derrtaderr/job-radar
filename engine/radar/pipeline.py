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

**Nothing added for row 64 suppresses anything.** The decision ledger and the
content fingerprints ATTACH to a row — a prior verdict, a "possible repost of
<jid>" flag, non-kill notes — and the row still reaches the queue with the score
it would otherwise have. A posting the human already judged, hidden on the
strength of that judgment, is the same failure as the judgment being forgotten:
they both mean the human never sees the decision again. The suppressions above
are unchanged, including the per-run (company, title) pair dedup, which stays
per-run precisely because the ledger is the cross-run mechanism.
"""
from __future__ import annotations

import hashlib

from engine.radar.fingerprint import fp_body, fp_comp, fp_equal
from engine.radar.ledger import prior_verdict
from engine.radar.rules_engine import kill_flags, score, seniority_notes, title_passes
from engine.radar.state import fingerprints, make_entry
from engine.radar.tracker import tracker_suppresses


def excluded(company, exclusions) -> bool:
    """Case-insensitive substring match against the never-surface list. Substring
    rather than exact, because "Northwind Analytics" and "Northwind Analytics,
    Inc." are the same employer and nobody should have to list both."""
    c = (company or "").lower()
    return any(x in c for x in exclusions)


def _repost_of(row_comp, row_body, known):
    """The earliest known jid whose fingerprints match this row, or None.

    Searched against the state this run is BUILDING, so it covers both a repost
    that arrived on an earlier day and one that arrived earlier in the same run —
    the within-run case the (company, title) dedup cannot see, because an
    aggregator posts under its own name and the pair differs.

    A legacy state entry has no fingerprints and `fp_equal` refuses to match two
    unknowns, so nothing recorded before this mechanism existed reads as a repost
    of anything.
    """
    for jid, entry in known.items():
        prior_comp, prior_body = fingerprints(entry)
        if fp_equal(prior_body, row_body) or fp_equal(prior_comp, row_comp):
            return jid
    return None


def pipeline(raw_rows, state, cfg, tracker_set, today, decisions=()):
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
        rid, url = r.get("id"), r.get("job_url")
        if rid or url:
            jid = str(rid or url)
        else:
            # No id and no URL: falling back to the literal string "None"
            # collapses every such row onto one jid, silently merging
            # distinct postings and — worse — falsely suppressing later ones
            # on the next run once "None" is in state. Derive a stable
            # synthetic id from content instead, so distinct postings keep
            # distinct identities and identical ones still dedupe.
            company = (r.get("company") or "").lower()
            title = (r.get("title") or "").lower()
            digest = hashlib.sha1(f"{company}|{title}".encode()).hexdigest()[:12]
            jid = f"noid-{digest}"
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

        # Everything below ATTACHES. Computed before this row's own entry lands
        # in new_state, so a row can never be reported as a repost of itself.
        row_comp, row_body = fp_comp(r), fp_body(r)
        attached = {
            "jid": jid,
            "prior": prior_verdict(r, decisions, new_state, jid),
            "repost_of": _repost_of(row_comp, row_body, new_state),
            "notes": seniority_notes(r, cfg),
        }
        new_state[jid] = make_entry(
            today, company=r.get("company"), title=r.get("title"),
            fp_comp=row_comp, fp_body=row_body)

        flags = kill_flags(r, cfg)
        if flags:
            killed.append(dict(r, flags=flags, **attached))
        else:
            survivors.append(dict(r, score=score(r, today, cfg), **attached))

    survivors.sort(key=lambda r: -r["score"])
    return survivors, killed, new_state
