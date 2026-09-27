"""The network adapter — the only module allowed to import JobSpy or touch
urllib. Everything the pipeline needs from a job board comes through here as
a plain list of dicts, so the rest of the engine never has to know JobSpy
exists.

JobSpy is imported inside `scrape()`, not at module scope, so this file
imports cleanly (and every test, `--dry-run`, and `--check` run cleanly)
without the dependency on the path at all.
"""
from __future__ import annotations

import re
import sys
import urllib.error
import urllib.request

_NAN_LIKE = ("nan", "NaT", "None", "<NA>")

# A backslash before any ASCII punctuation character — markdown's escape rule.
# Deliberately NOT a backslash before anything: `C:\new` and `\d+` appear in real
# postings, and stripping those backslashes would silently edit a path or a regex
# a posting quoted on purpose.
_MD_ESCAPE = re.compile(r"\\([!-/:-@\[-`{-~])")

_USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")


def unescape_markdown(text):
    """Remove markdown backslash escapes from a posting body.

    **This is the one place in the repo that knows a description is markdown**,
    and it is why the rest of the engine can treat a body as plain prose. A live
    LinkedIn scrape hands back `description` as markdown, and JobSpy escapes its
    punctuation, so the wire text reads:

        "This is a fully on\\-site position"

    Every kill pattern downstream is written against prose — `on-?site`,
    `in[- ]office`, `remote[- ]first`, `100 ?% remote` — and none of them match
    across a backslash. The on-site rule returned NO flags on real postings while
    passing every prose fixture in the suite, which is the failure this closes.

    The normalisation lives here rather than in `rules_engine` or `pipeline` for
    two reasons: this module is already the only one that knows what JobSpy is, and
    the pipeline stays a pure function over plain text, so nothing downstream has
    to remember to clean its input. It also means a body is unescaped BEFORE it is
    fingerprinted, so an original and a repost cannot differ by punctuation alone.
    """
    if text is None:
        return None
    return _MD_ESCAPE.sub(r"\1", str(text))


def _normalize_frame_rows(frames) -> list:
    """Flatten JobSpy's per-query DataFrames into plain dicts.

    A `None` frame (a query that returned nothing) is skipped. Within a row,
    any value whose str() reads as pandas' various flavors of "no value"
    (NaN, NaT, None, <NA>) becomes a real `None`, and `date_posted` is
    truncated to its date portion — JobSpy hands back a full timestamp, and
    downstream only ever wants the day.

    `description` additionally has its markdown escapes removed here — see
    `unescape_markdown`. Only `description`: a title or a location arrives as a
    plain string, and touching those would be a second normalisation point with
    no reason to exist.
    """
    rows = []
    for frame in frames:
        if frame is None:
            continue
        for _, row in frame.iterrows():
            d = {k: (None if str(v) in _NAN_LIKE else v)
                 for k, v in row.to_dict().items()}
            if d.get("date_posted") is not None:
                d["date_posted"] = str(d["date_posted"])[:10]
            if "description" in d:
                d["description"] = unescape_markdown(d["description"])
            rows.append(d)
    return rows


def scrape(cfg) -> list:
    """Run every configured query against JobSpy and hand back one flat,
    normalized list of JobSpy-shaped row dicts.

    A query that raises (rate limit, bot wall, transient network error) is
    reported and skipped — one bad query must not sink the rest of the run.
    """
    import jobspy

    frames = []
    for term in cfg.queries:
        try:
            frames.append(jobspy.scrape_jobs(
                site_name=cfg.sites,
                search_term=term,
                location=cfg.search_location,
                results_wanted=cfg.results_per_query,
                hours_old=cfg.hours_old,
                linkedin_fetch_description=True,
            ))
        except Exception as e:
            print(f"  query '{term}' failed: {e}")
    return _normalize_frame_rows(frames)


def http_fetch(url, timeout=15):
    """Thin network adapter for check_postings. Returns (status, body).

    HTTPError carries the status we care about (404/410 are the real
    signal), so it is unwrapped rather than raised. Anything else propagates
    — the caller (check_postings) turns an unexpected exception into
    "unknown" rather than a crash.
    """
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
