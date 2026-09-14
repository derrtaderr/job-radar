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
