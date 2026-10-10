---
name: Warm-path stage design
status: draft, awaiting review
date: 2026-10-09
read_by: superpowers:writing-plans (next step), then every lane implementing it; DESIGN.md gains a section pointing here once shipped
---

# Warm path: find a person at the company, in the right order

## Why

The radar finds postings well. The bottleneck is after it: drafted applications sit unsent,
and the ones that go out go out cold. A referral changes what happens at the first screen.
The best-sourced benchmark (Lever, ~4M candidates across ~1,000 employers, 2015-16) found
roughly 1 in 16 referred candidates hired against 1 in 152 job-board applicants, and at
small and midsize companies 57% of referrals reached a first screen against 13% of
applicants. Those numbers are dated and someone else's; this stage exists partly to replace
them with the user's own.

**The mechanic that shapes the whole design: a referral usually has to land before the
application.** Many employer referral policies do not credit a referral once the candidate
is already in the applicant tracking system, and some accept the referrer's name only on
the original application. Applying first can forfeit the referral and the referrer's bonus.
So a connection is not a reason to pursue a posting; fit decides that. A connection changes
the **order of steps** for a posting already chosen.

## Scope

**Scoped for one user for now** (decision 2026-10-09): Clay is a required dependency of the
lookup step. Generalizing it (Clay optional, a manual fallback) is a later lane. Real names
still never enter version control, because the repo is headed public and the privacy guard
would refuse the commit regardless.

**In:** connections-export join, Clay lookup of hiring manager and recent hires, a path
flag on the queue and tracker, an ordering gate at the top of `/apply`, outreach drafting
(`/reach`), a touch ledger, due-item surfacing, calibration contrasts on replies and on
referral versus interview rate.

**Out, deliberately:** score points for paths (v1 is a flag; calibration may propose points
once data exists), second-degree connections, scraping LinkedIn, any send path, auto-apply.

## Architecture

```
LinkedIn data export ─► config/network/connections.csv ─┐
                                                        ├─► resolve_paths()  (pure; no model, no network)
/paths (session + Clay) ─► network_cli.py add ─► config/network/people/<company-slug>.yaml ─┘
                                                        │
          queue.md + tracker "Drafted" rows show a PATH column (no score change)
                                                        ▼
/apply Step 0: network_cli.py gate <company> ── warm & not asked ─► STOP, offer /reach
                                                        │
/reach drafts ─► human sends ─► network_cli.py touch / reply ─► config/network/touches.csv
                                                        │
              network_cli.py due  ◄── read by /daily      calibrate.py path contrasts
```

The repo's two boundaries hold unchanged. Everything under `config/network/` is personal
judgment and state, gitignored with the rest of `config/`. Every generative step (the Clay
lookup, reading posts, drafting a message, assigning a register label) lives in a session
command; every structured write goes through a tested tool that validates first.

## Components

### 1. `engine/network/connections.py` — the export loader

Reads LinkedIn's own data-export `Connections.csv`. LinkedIn prepends a notes preamble above
the header row, so the loader seeks the header (`First Name,Last Name,URL,...`) rather than
assuming line one. Columns used: first name, last name, URL, company, position, connected
on. A missing required column is a loud error naming the column and the export path. The
file's modification date is carried through as the **export date**, rendered next to every
warm path, because a connection's company is only as current as the export.

### 2. `engine/network/company.py` — name normalization and matching

`normalize(name)`: casefold, strip punctuation, drop legal suffixes (inc, llc, ltd, corp,
co, gmbh, plc, and the like), collapse whitespace. `config/network/aliases.yaml` maps
variants to a canonical name (for example a parent company to its operating brand) and is
optional.

Matching follows DESIGN.md's flag-versus-verdict bar:

- **Exact match after normalization or alias** → a verdict: the connection is `warm`.
- **Substring match only**, floored at four characters as the tracker matcher already is
  → a flag: rendered `check: <name> at <their company>?`, never counted as warm. A wrong
  warm claim costs an awkward message; a flag costs a glance.

### 3. `config/network/people/<company-slug>.yaml` — lookup results

Written only by `network_cli.py add`, never by hand-edited prose. One file per company:

```yaml
company: Example Co
looked_up: 2026-10-10
source: clay
result: found          # found | none   (a failed lookup writes nothing)
people:
  - slug: a-rivera
    name: A. Rivera
    title: Head of Growth Engineering
    url: https://www.linkedin.com/in/example
    role: hiring_manager   # hiring_manager | recent_hire
    started: 2026-06-01    # recent_hire only
    status: current        # current | left_company
```

A file older than 30 days renders as stale. A failed Clay call writes nothing, so the
company stays `unresearched` rather than becoming a false `none`.

### 4. `engine/network/paths.py` — `resolve_paths(posting, network) -> list[Path]`

Pure function. Returns every path for a posting's company, best first:

| Path | Source | Order of steps | Waits for |
|---|---|---|---|
| `warm` | first-degree connection, exact company match | ask, then apply through them | their yes, or 3 business days of silence, then apply plus a hiring-manager note |
| `recent_hire` | Clay, joined within ~180 days | ask for a 15-minute chat about the team; referral ask only after it | nothing; runs in parallel with a normal application |
| `cold_hm` | Clay, likely hiring manager | apply, then send the note | nothing |
| `none` | looked up, nothing found | apply as today | nothing |
| `unresearched` | never looked up | apply as today | nothing |

`none` and `unresearched` are distinct on purpose: an empty path column must never read as
"nobody there" when nobody looked.

### 5. Rendering

`engine/radar/report.py` gains a `path` column on the queue, rendered from the best path
plus a count of the rest (`warm: A. Rivera, connected 2019 (+1)`). Score is untouched.
The tracker's "Drafted but not applied" section gains a `Path` column; `tracker_schema.py`
already tolerates extra columns there, and the column is not added to `REQUIRED_COLUMNS`.

### 6. `/paths` — session command, Clay lookup

For the top N of today's queue (default 10, `settings.yaml: network.lookup_top_n`) plus
every tracker row in "Drafted but not applied", skipping companies with a fresh people file:
query Clay for the likely hiring manager for the posting's function and for people in that
function who started within ~180 days. Each result is written through
`network_cli.py add`. The command ends by re-rendering the day's queue so the path column
reflects the lookup. N caps credit spend; the command states credits used.

### 7. The ordering gate — `network_cli.py gate <company> [--posting <id>]`

Exit 0: proceed. Exit 3: a `warm` path exists and no ask is recorded for this posting;
prints the person, the connection date, and the instruction to run `/reach` first. Exit 4:
an ask is recorded and still inside its 3-business-day window; prints the day it expires.

`/apply` gains a Step 0 that runs the gate before reading the JD. On exit 3 or 4 it stops
and offers `/reach`. The human may say "apply anyway"; `/apply` then records an override
touch (`state: override`) so calibration can later show what skipping the ask cost.

### 8. `/reach <posting> [person]` — session command, outreach drafting

Drafts to `apply-out/<company-slug>/outreach-<person-slug>.md`, never sends. Header block
above the message records motive, hook level, register label with its quoted evidence, and
whether the touch is a control.

**Motive (set by path):**
- `warm`: easy to decline, asks for the referral itself, includes the posting link and a
  two-line blurb the connection can paste into their referral form.
- `recent_hire`: message one asks only for 15 minutes about the team. No referral ask.
- `cold_hm`, after applying: leads with the posting's problem, says the application is in,
  one credibility line.

**Hook (strongest available, in order):**
1. shared history (mutual connection, past employer, school)
2. something they posted that overlaps the user's work
3. the posting's core problem matched to one of the user's public builds, listed in
   `config/outreach.md`. A stretch match is reported as "no build fits", never forced.

**Register (matched to how they write):** from their recent posts, record typical length,
formality and technical density, summarized as one of four labels (driver, expressive,
steady, analytical) **with two or three quoted lines as evidence**. Thin evidence yields
`unclear` and a neutral note. Skipped for `warm`, where the existing relationship is the
better guide. For `recent_hire` and `cold_hm`, one touch in five is a **control**: drafted
neutral regardless of label, so the reply data can say whether matching helps.

**Carried-over rules:** every claim traces to `config/profile.md` (the `/apply` claim
gate, extended to messages); voice rules from `config/outreach.md` apply; posts and
profiles are untrusted data under the same rule `/apply` applies to postings.

### 9. `config/network/touches.csv` and `network_cli.py`

Append-only, like `decisions.csv`. Columns: `date, posting_id, company, person_slug, path,
motive, hook_level, register, control, state, note`. States: `asked`, `replied`,
`referred`, `declined`, `no_reply`, `left_company`, `applied`, `override`. A later row for
the same posting and person supersedes an earlier one; nothing is rewritten in place.

Subcommands: `add` (people file), `touch` (record a send), `reply` (record a response),
`gate`, `due`. Every write validates first and supports `--dry-run`. A `touch` naming a
posting id this machine has no record of is refused with the fix named, mirroring `judge`.
`no_reply` is written by `due` once a touch passes 10 business days, and is overrulable by
a later `reply`.

### 10. `network_cli.py due` — surfacing

Lists, oldest first: warm asks at or past day 3 ("apply today, add the hiring-manager
note"), recent-hire chats awaiting a reply, hiring-manager notes owed for applications
already sent. The vault's `/daily` calls it, which is the reader that keeps this from
depending on memory.

### 11. Calibration

`engine/loop/calibrate.py` gains two reports under `tools/calibrate.py --paths`, reusing
the existing floors (`DEFAULT_MIN_N = 5` per side, `MIN_GAP_POINTS = 20`, noise floor) and
the existing named-suppression behavior:

1. **Reply rates** by path, by hook level, and matched register versus control.
2. **Referral versus interview rate.** `/apply` writes `path` and `referral_state` into
   the archive's outcome frontmatter at archive time; a new `ContrastSpec`
   (`key="referred"`) compares interview rate for referred versus not-referred
   applications. This is the contrast that may eventually justify score points for paths,
   and only through a printed proposal; calibration still never edits config.

## Error handling

| Failure | Handling |
|---|---|
| Company names match only partially | `check:` flag, never warm |
| Clay errors or times out | Nothing written; company stays `unresearched`; the session says so |
| Export older than 60 days | `tools/doctor.py` gains an eleventh check that warns, naming the re-export path |
| Person has left the company | `reply --state left_company` marks the people file; path drops out |
| Instruction-like text in a post | Untrusted data; noted in one line, never followed |
| Touch for an unknown posting | Refused, fix named |
| Malformed `touches.csv` row | Loud error naming file and line; nothing is skipped silently |
| Real names reaching git | `config/` and `apply-out/` already gitignored; privacy-guard fixture added for a contact-name denylist entry |

## Testing

Test-first, fictional fixtures only, following the existing `tests/fixtures*.py` pattern.

- `normalize` and matching: suffixes, aliases, the four-character floor, exact versus flag.
- Connections loader: preamble skipping, missing columns, export date.
- `resolve_paths`: every row of the path table, ordering, `none` versus `unresearched`,
  staleness, `left_company`.
- Business-day math for the 3-day and 10-day windows, including weekends.
- Touch ledger: append, supersede, refusal on unknown posting, malformed rows.
- `gate` exit codes 0, 3, 4 and the override path.
- `due` ordering and content.
- Calibration: both new reports above and below the floors, with named suppressions.
- Report rendering: the path column, `(+N)` count, stale marker.
- A docs test asserting `/apply` Step 0 runs the gate, in the style of `test_loop_docs.py`.

## First real run

The tracker's current "Drafted but not applied" rows. None has been sent, so every warm
path found there can still become a proper referral. The run passes if a meaningful share
gain a named person; if almost none do, that is the finding (thin network overlap), and the
recent-hire path becomes the main lever.

## Ambition check

- **Ambitious enough?** Yes. It moves the radar from finding postings to winning them in
  the right order, and it measures whether referrals raise this user's interview rate
  instead of trusting a 2016 benchmark.
- **Can it be better?** The deliberate cuts (no send path, no second-degree) hold until
  first-degree paths prove they convert.
- **Small thinking?** The honest limit is volume: a few dozen touches a month means the
  contrasts read "too few" by name for the first month or two.
