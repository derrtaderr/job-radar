"""Fixture tracker markdown for engine/loop/tracker_schema.py tests.

Every company here is fictional (Cobalt Grid, Meridian Analytics, Tessellate,
Harborlight, Pinecrest Software, Voss Continuum, Northwind Analytics) — none of
this describes a real search. Column headers and section names ARE the real
house tracker shape (the Global Constraints contract): the point of these
fixtures is to exercise that exact shape, not a stand-in for it.
"""

VALID_TRACKER = """\
## Active

| Company | Role | Source | Stage | Comp band | Last touch | Next step | Notes |
|---|---|---|---|---|---|---|---|
| Cobalt Grid | Data Platform Engineer | LinkedIn | HM round | 150-180k | 2026-09-10 | Send follow-up | Strong tech fit |
| Harborlight (via referral) | Senior Data Engineer | Referral | Screen | 160-190k | 2026-09-12 (sent reply) | Await scheduling | Warm intro from Alex |
| Voss Continuum | Data Engineer | Cold outreach | Applied | 130-155k | 2026-09-11 | Wait for response | None yet |

## Drafted but not applied

| Company | Role | Source | Comp band | Resume | Next step | Notes |
|---|---|---|---|---|---|---|
| Meridian Analytics | Analytics Engineer | Job board | 140-165k | v3 | Finish cover letter | JD emphasizes SQL |

## Research (JD filed, no work started)

| Company | Role | Comp band | Lean | Notes |
|---|---|---|---|---|
| Tessellate | Platform Engineer | 145-170k | Lean yes | Series B, remote-first |
| Pinecrest Software | Data Engineer | Unlisted | Lean no | Onsite only |

## Closed

| Company | Role | Date closed | Outcome | Reason | Carry-forward lesson |
|---|---|---|---|---|---|
| Meridian Rows | Data Engineer | 2026-08-20 | Rejected | Final round, lost to internal candidate | Ask about internal candidates earlier |
| Northwind Analytics | Data Platform Engineer | 2026-07-15 | Withdrew | Comp band below floor | Confirm comp band before HM round |
"""

# --- broken variants, one violation class each ---

MISSING_ACTIVE_SECTION = """\
## Closed

| Company | Role | Date closed | Outcome |
|---|---|---|---|
| Meridian Rows | Data Engineer | 2026-08-20 | Rejected |
"""

MISSING_CLOSED_SECTION = """\
## Active

| Company | Role | Last touch |
|---|---|---|
| Cobalt Grid | Data Platform Engineer | 2026-09-10 |
"""

MISSING_REQUIRED_COLUMN_ACTIVE = """\
## Active

| Company | Role | Source |
|---|---|---|
| Cobalt Grid | Data Platform Engineer | LinkedIn |

## Closed

| Company | Role | Date closed | Outcome |
|---|---|---|---|
| Meridian Rows | Data Engineer | 2026-08-20 | Rejected |
"""

MISSING_REQUIRED_COLUMN_CLOSED = """\
## Active

| Company | Role | Last touch |
|---|---|---|
| Cobalt Grid | Data Platform Engineer | 2026-09-10 |

## Closed

| Company | Role | Date closed |
|---|---|---|
| Meridian Rows | Data Engineer | 2026-08-20 |
"""

CELL_COUNT_MISMATCH = """\
## Active

| Company | Role | Last touch |
|---|---|---|
| Cobalt Grid | Data Platform Engineer |

## Closed

| Company | Role | Date closed | Outcome |
|---|---|---|---|
| Meridian Rows | Data Engineer | 2026-08-20 | Rejected |
"""

BAD_ISO_DATE_ACTIVE = """\
## Active

| Company | Role | Last touch |
|---|---|---|
| Cobalt Grid | Data Platform Engineer | TBD |

## Closed

| Company | Role | Date closed | Outcome |
|---|---|---|---|
| Meridian Rows | Data Engineer | 2026-08-20 | Rejected |
"""

BAD_ISO_DATE_CLOSED = """\
## Active

| Company | Role | Last touch |
|---|---|---|
| Cobalt Grid | Data Platform Engineer | 2026-09-10 |

## Closed

| Company | Role | Date closed | Outcome |
|---|---|---|---|
| Meridian Rows | Data Engineer | recently | Rejected |
"""

DUPLICATE_COMPANY_ROLE = """\
## Active

| Company | Role | Last touch |
|---|---|---|
| Cobalt Grid | Data Platform Engineer | 2026-09-10 |
| Cobalt Grid | Data Platform Engineer | 2026-09-11 |

## Closed

| Company | Role | Date closed | Outcome |
|---|---|---|---|
| Meridian Rows | Data Engineer | 2026-08-20 | Rejected |
"""

# Closed (and Research) are append-only by design — a company can reasonably
# apply for the same role months apart (reactivation, a second req). Only
# Active and Drafted but not applied gate on duplicate Company+Role, because
# a role can't be live twice AT ONCE. Orchestrator ruling, 2026-09-13.
DUPLICATE_IN_CLOSED_ALLOWED = """\
## Active

| Company | Role | Last touch |
|---|---|---|
| Cobalt Grid | Data Platform Engineer | 2026-09-10 |

## Closed

| Company | Role | Date closed | Outcome |
|---|---|---|---|
| Crux | GTM Engineer | 2026-05-27 | No-fit (role pivoted) |
| Crux | GTM Engineer | 2026-09-02 | Closed-lapsed (own action) |
"""

DUPLICATE_IN_DRAFTED_STILL_FLAGGED = """\
## Active

| Company | Role | Last touch |
|---|---|---|
| Cobalt Grid | Data Platform Engineer | 2026-09-10 |

## Drafted but not applied

| Company | Role | Comp band |
|---|---|---|
| Meridian Analytics | Analytics Engineer | 140-165k |
| Meridian Analytics | Analytics Engineer | 145-170k |

## Closed

| Company | Role | Date closed | Outcome |
|---|---|---|---|
| Meridian Rows | Data Engineer | 2026-08-20 | Rejected |
"""

# A cell carrying a literal "|" written as "\|" — what the radar's own report
# renderer produces — must parse as ONE cell, not split the row in two.
ESCAPED_PIPE_CELL = """\
## Active

| Company | Role | Last touch |
|---|---|---|
| Cobalt Grid | Growth \\| Ops Engineer | 2026-09-10 |

## Closed

| Company | Role | Date closed | Outcome |
|---|---|---|---|
| Meridian Rows | Data Engineer | 2026-08-20 | Rejected |
"""

# One more cell than the header count — the overflow cell must be dropped
# from the Row (not silently attached under a made-up key), and the mismatch
# must still be reported by line, same as the too-FEW-cells case.
MORE_CELLS_THAN_HEADERS = """\
## Active

| Company | Role | Last touch |
|---|---|---|
| Cobalt Grid | Data Platform Engineer | 2026-09-10 | Extra cell |

## Closed

| Company | Role | Date closed | Outcome |
|---|---|---|---|
| Meridian Rows | Data Engineer | 2026-08-20 | Rejected |
"""

# An overflow row (more cells than headers) keeps its LEADING cells aligned
# with the headers — only the excess trailing cell(s) are unpositioned. So
# unlike the too-FEW-cells case, the ISO-date and duplicate checks still
# apply to those leading cells; the cell-count violation fires either way.
# Here Last touch is the row's 3rd (aligned) cell and carries a bad date.
OVERFLOW_ROW_WITH_BAD_DATE_IN_ALIGNED_COLUMN = """\
## Active

| Company | Role | Last touch |
|---|---|---|
| Cobalt Grid | Data Platform Engineer | TBD | Extra cell |

## Closed

| Company | Role | Date closed | Outcome |
|---|---|---|---|
| Meridian Rows | Data Engineer | 2026-08-20 | Rejected |
"""

# Same idea for the duplicate-Company+Role check: two overflow rows whose
# leading Company/Role cells are aligned and identical must still be flagged,
# even though each row also carries an extra trailing cell.
OVERFLOW_ROWS_WITH_DUPLICATE_IN_ALIGNED_COLUMNS = """\
## Active

| Company | Role | Last touch |
|---|---|---|
| Cobalt Grid | Data Platform Engineer | 2026-09-10 | Extra one |
| Cobalt Grid | Data Platform Engineer | 2026-09-11 | Extra two |

## Closed

| Company | Role | Date closed | Outcome |
|---|---|---|---|
| Meridian Rows | Data Engineer | 2026-08-20 | Rejected |
"""

# A row short one cell shifts every later column left by one position — the
# shape of a real malformed row found on a live tracker (5 cells vs 6
# headers). Once the cell count is wrong, column identity can't be trusted,
# so the shifted "Date closed" position landing on prose with no ISO date
# must NOT also fire — one real bug, one violation, not two symptoms of the
# same row.
CELL_COUNT_MISMATCH_SUPPRESSES_DOWNSTREAM_CHECKS = """\
## Active

| Company | Role | Last touch |
|---|---|---|
| Cobalt Grid | Data Platform Engineer | 2026-09-10 |

## Closed

| Company | Role | Date closed | Outcome |
|---|---|---|---|
| Tempo Corp | GTM Engineer | Outbound app, resurrected later, screen cancelled |
"""
