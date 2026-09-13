"""The network adapter — the only module allowed to import JobSpy or touch
urllib. Everything the pipeline needs from a job board comes through here as
a plain list of dicts, so the rest of the engine never has to know JobSpy
exists.

JobSpy is imported inside `scrape()`, not at module scope, so this file
imports cleanly (and every test, `--dry-run`, and `--check` run cleanly)
without the dependency on the path at all.
"""
from __future__ import annotations

import sys
import urllib.error
import urllib.request

_NAN_LIKE = ("nan", "NaT", "None", "<NA>")

_USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")


def _normalize_frame_rows(frames) -> list:
    """Flatten JobSpy's per-query DataFrames into plain dicts.

    A `None` frame (a query that returned nothing) is skipped. Within a row,
    any value whose str() reads as pandas' various flavors of "no value"
    (NaN, NaT, None, <NA>) becomes a real `None`, and `date_posted` is
    truncated to its date portion — JobSpy hands back a full timestamp, and
    downstream only ever wants the day.
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
