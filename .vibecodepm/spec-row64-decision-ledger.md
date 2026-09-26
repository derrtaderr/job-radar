---
name: Row 64 spec — decision ledger, repost fingerprints, four rule types
read_by: the reviewer of lane/row64-decision-ledger, and any session that later changes the
  ledger, the state-file shape, the location/on-site/hybrid/seniority rules, or the queue
  columns — this file is where the divergences and the non-goals are recorded
milestone: row 64 (judgment that is not machine-readable does not compound)
status: current — matches the build at lane/row64-decision-ledger
date: 2026-09-26
supersedes: none
---

# Row 64 — judgment that is not machine-readable does not compound

## The problem this closes

The engine is deterministic: scrape, kill, score, report. The human reads the top survivors'
JDs each morning and decides. **That decision has had nowhere to go.** It was recorded as
prose in a markdown tracker nothing parses, so the next run could not see it, and a req the
human read and killed by hand came back days later as the top-scored row. Third re-surface
of that kind in four days.

Six dated misses from live runs motivate this row. Each one gets a named mechanism below and
a case in the synthetic replay test (`tests/test_row64_replay.py`).

| # | Miss | Mechanism |
|---|---|---|
| 1 | A hand-killed req re-surfaced as the top row; the kill was unparseable prose | A. decision ledger |
| 2 | Aggregator reposts and same-req-different-territory duplicates defeat suppression | B. content fingerprints |
| 3 | The location rule resolved "New York, United States" two ways on one day | C1. location normalisation |
| 4 | "This is a fully on-site position" in the body did not kill | C2. negative body override |
| 5 | "Tuesdays and Fridays are remote/work from home days" passed as remote (4 instances) | C3. tightened remote override |
| 6 | "1-4 years of relevant experience, early in their career" placed second | C4. seniority band |

## Prior art read before designing

- **`engine/radar/pipeline.py`** — the one place a run's decisions are made, a pure function
  over (rows, state, cfg, tracker_set, today). Suppressions are ordered cheap-and-certain
  before expensive-and-fallible, and a row suppressed by the tracker or exclusions is
  deliberately NOT written to state so removing a line brings the company back. The
  `(company, title)` pair dedup at the end is **per-run only** — `seen_pairs` is a local set,
  born and discarded inside one call.
- **`engine/radar/tracker.py::tracker_suppresses`** — normalises both sides and matches by
  substring in either direction with a 4-character floor, because the scrape and the tracker
  are written by different authors. The ledger's company/title matching borrows this instinct
  but not the code: a ledger row is machine-written by our own CLI, so it does not need
  substring tolerance in both directions, and a 4-char substring match on titles would
  collapse "Data Engineer" into "Data Engineering Manager".
- **`engine/radar/state.py`** — one file, one dict, `jid -> "YYYY-MM-DD"`, deliberately dumb
  and deliberately readable. A corrupt file warns and degrades to empty rather than crashing
  a run.
- **The `_jd_says_remote` override machinery in `rules_engine.py`** — `_REMOTE_OK` finds
  affirmative remote language, `_NEG` rejects a match negated within a 30-char window before
  or to the end of the sentence after. `_OFFICE_CADENCE` already defeats the override
  **document-wide**. Its `work from home [A-Z][a-z]+days` alternation catches "work from home
  Fridays" but not "Fridays are work from home days" — the day names arrive before the
  phrase, which is exactly miss 5.
- **`evidence()`** — every kill quotes a ±40-char window of the posting. Every new rule here
  quotes its evidence the same way. A flag without a quote is not shippable in this repo.

## The mechanisms

### A. Decision ledger

`config/decisions.csv`, machine-readable, in the user's gitignored `config/` directory.
Columns: `jid, company, title, verdict, reason, date, url`. Verdict enum is closed and small:
`kill` (the human's judgment ruled it out) and `draft` (the human chose to pursue it).
`reason` is a free short slug, e.g. `bi-analytics`.

Written by a new CLI verb:

```
radar.py judge <jid> --verdict kill --reason bi-analytics
radar.py judge --company "Northwind Analytics" --title "Data Engineer" --verdict draft --reason strong-fit
```

Read by the pipeline before ranking. **A previously judged posting is never hidden.** A
scraped row that matches a ledger row renders in the queue with its prior verdict and reason
attached in a `Prior` column, so the bench stays a bench and the human stays the final gate.

**Ledger matching, in order** (the orchestrator's addendum of 2026-09-26, verified against
the real day folders):

1. **exact `jid`**
2. **normalised `(company, title)` pair**
3. **body fingerprint** (mechanism B), via the earlier jid's fingerprints in `state.json`

Tier 2 exists because the motivating case re-surfaced **under a new posting id**: same
company, same title, same body, a new LinkedIn id because the board reissued the req. Tier 1
alone would have missed it. This is why a ledger row needs `company` and `title` populated
even when it was written by jid — see the divergence on state contents below.

### B. Content fingerprints

Two fingerprints per posting, persisted in `state.json` so matching works across days:

- **`fp_comp`** — the comp band (min/max/interval, or the body-stated max) plus the sorted
  set of benefit tokens found in the body. Sorted and set-valued so a reworded benefits block
  still matches. `None` when a posting carries neither a comp band nor any benefit token: a
  fingerprint of nothing would match every thin posting to every other, which is the
  false-merge failure this is supposed to prevent.
- **`fp_body`** — `sha1(normalised title + body)` with the territory/location tokens
  stripped (compass territories like "Eastern US", `", United States"` / `", US"` / `", USA"`
  suffixes, US state names and abbreviations) and the row's own company name removed.

The two are complementary, and the reason is the two shapes of miss 2. A
**same-req-different-territory** duplicate ("Eastern US" / "Western US") has an identical body
once the territory token is gone, so `fp_body` catches it. An **aggregator repost** replaces
the client's name with the board's and anonymises the client in the prose, so the body
genuinely differs and `fp_body` cannot bridge it — but the comp band and the benefits block
are copied verbatim, so `fp_comp` catches it.

A survivor whose fingerprint matches an earlier jid is **flagged**, never suppressed:
`possible repost of <jid>`. If that earlier jid carries a ledger verdict, the verdict is
attached too. Never suppress on fingerprint alone — the aggregator copy sometimes carries
detail the original lacks.

### C. Four rule types

All four are config-driven with a fictional instance in `config.example/`, which is how
Phase 1 shipped every rule.

**C1. Location normalisation before matching.** `normalise_location()` lowercases, collapses
whitespace, strips `", United States"` / `", US"` / `", USA"` / `", U.S."`, maps full US state
names to their two-letter abbreviation, and dedupes the comma-separated parts. So "New York,
United States", "New York, NY" and "NY" all resolve to `ny`, and one spelling can no longer
resolve two ways.

The commute allowlist is then matched **on word boundaries within the normalised parts**,
never as a bare substring of the raw string. This closes the specific way miss 3 happens: a
commute pattern of `NY` substring-matches "Pennsylvania, United States" (…syl**va**nia →
`ny` at index 9) while missing "New York, United States" entirely. Word-bounded matching on
normalised parts rejects `pennsylvania` and accepts `ny`, and still accepts a pattern of
`Denver` against `denver tech center`, which a `fullmatch` would have broken.

**C2. Negative body override** (`onsite_phrases` in `rules.yaml`). Symmetric to the
affirmative `_jd_says_remote` override: "fully on-site", "on-site position/role", "100%
on-site", "in office N days", "N days a week in the office" produce an `onsite-body` flag with
the matched line quoted, **even when the header location passes and even when `is_remote` is
true** — a body that says fully on-site against an `is_remote` header is a contradiction, and
the scraper's flag is the less reliable of the two. Negated matches are skipped through the
existing `_NEG` window ("not an on-site position").

The one thing it must not override is the **commute allowlist**: an on-site role in a city
the user can commute to is a role they want. So the allowlist is checked first and wins.
`config.example`'s demo row `demo-4` (Tessellate, "in-office role based out of our Denver
headquarters", `Denver, CO`, commute pattern `Denver|Boulder`) exercises exactly that path and
must keep surviving.

**C3. Tightened affirmative-remote override** (`hybrid_phrases` in `rules.yaml`). The override
must describe the **role** as remote. For each `_REMOTE_OK` match, the containing **sentence**
is checked for day-of-week names, hybrid phrasing, and in-office cadence; a match in the same
sentence rejects that match and the walk continues to the next one. The existing
document-wide `_OFFICE_CADENCE` check stays, because removing it would loosen current
behavior. Sentence scope is what catches miss 5: "Tuesdays and Fridays are remote/work from
home days" fires `_REMOTE_OK` on "work from home" and names in-office days in the same breath.

**C4. Years-of-experience, reading both ends of the band** (`seniority` in `rules.yaml`, keys
`min_years`, `penalty`, `stretch_years`).

- A **floor** below `min_years` — `"1-4 years"`, `"0-3 years"`, `"early in their career"`,
  `"entry level"`, `"new grad"` — applies a **score penalty**, not a kill, and surfaces as a
  quoted `junior-band` flag.
- An **upper stretch** at or above `stretch_years` (`10+ years`) sets a `seniority-stretch`
  flag, not a kill.

A penalty rather than a kill because a band is weak evidence about a req: boards and
recruiters mislabel seniority constantly, and miss 6's complaint was ranking, not visibility.

### D. No LLM call anywhere

Nothing here calls a model. Deterministic rules kill and score; judgment happens in the
human's session and comes back through the ledger. This is the project's thesis and the whole
reason the ledger is a CSV the human writes with one command rather than a classifier.

### E. Privacy

Every fixture is synthetic: invented companies, invented JD text, `example.com` URLs,
`example.com` addresses, `555-01xx` numbers. No posting, company name, address or number from
a real run enters the repo. `python tools/privacy_guard.py` exits 0 at every commit, enforced
by the `.githooks` pre-commit hook and by CI.

## Divergences from the dispatch, with reasons

1. **The ledger path is `<config_dir>/decisions.csv` by convention, with no `decisions:` key
   in `settings.yaml`.** The dispatch said the doctor checks "the ledger, if configured". The
   precedent for a judgment file that lives in `config/` without a settings key is
   `profile.md`, read as `config_dir / "profile.md"` by both the drafting side and doctor
   check 6. Every settings-keyed path resolves against `config_dir.parent`, which would make
   `config.example`'s own shipped ledger unreadable when you run `--config config.example`
   (the path would resolve to `<repo>/config/decisions.csv`), and would add one more string a
   user can mistype into a permanently silent no-op. "If configured" therefore reads as "if
   present". Absent means nothing has been judged yet, which is the honest day-one state and
   a SKIP, not a FAIL.

2. **`state.json` entries carry `company` and `title` in addition to `seen`, `fp_comp` and
   `fp_body`.** The dispatch specified the value dict as `{"seen", "fp_comp", "fp_body"}`. The
   addendum then required tier-2 `(company, title)` matching, which needs those two fields
   populated on the ledger row even when `judge` is called with only a jid. `state.json` is
   already the per-jid record of what a run saw, it already lives in the same gitignored
   `config/` as the ledger it feeds, and reading them from there is deterministic where
   parsing them back out of `queue.md` or a `jd/*.md` frontmatter line is not (and the JD file
   only exists when the posting had a description). So `judge <jid>` backfills company and
   title from state, and refuses with a named fix when the jid is unknown and neither flag was
   passed.

3. **The `(company, title)` dedup in `pipeline.py` stays per-run.** Per the addendum,
   explicitly NOT extended to cross-run suppression. The ledger and the fingerprints are the
   cross-run mechanism and they **attach**, never hide.

4. **`decisions.csv` accepts `#` comment lines.** Not in the dispatch. `exclusions.txt`
   already has this convention, and it is what lets the shipped
   `config.example/decisions.csv` explain what it is to the stranger who opens it.

5. **The demo's twelve canned rows are not extended.** `config.example/decisions.csv` ships
   one fictional `kill` verdict against an existing demo posting, so `tools/demo.py`'s
   `queue.md` demonstrates the headline feature (a prior verdict attached to a re-surfaced
   row) with no change to the pinned survivor/kill counts. The four rule types are covered by
   the synthetic replay test instead. Adding demo rows would move
   `EXPECTED_SURVIVOR_COUNT`/`EXPECTED_KILL_COUNT`, which exist precisely to make that a
   deliberate decision, and the row did not ask for it.

## Non-goals, named so they are not mistaken for omissions

- **A prior `kill` verdict applies no score penalty and no re-ranking.** It attaches. The row
  says the bench remains a bench and the human stays the final gate; ranking a judged row
  down is a different decision, and inventing it here would quietly reintroduce hiding by
  another name. Open question below.
- **The ledger never suppresses.** The already-seen rule in `state.json` still suppresses by
  jid, as it always has. That is the seen-rule, not the ledger, and this row does not touch it.
- **No fuzzy/substring company matching in the ledger.** Tier 2 normalises and compares
  exactly. Substring matching on titles collapses distinct seniorities.
- **No LLM, no telemetry, no network.**

## Per-area gate set

Run from the worktree root, all of them, every cycle:

```bash
.venv/bin/python -m pytest -q                      # 574 at BASE
.venv/bin/python tools/privacy_guard.py            # must exit 0
.venv/bin/python tools/doctor.py --config config.example   # must exit 0
.venv/bin/python tools/demo.py --out /tmp/demo-row64       # CI runs it; must stay green
```

The README-claims check is `tests/test_readme_claims.py` (every `tools/*.py` path and
`` `/command` `` the README names must exist, the no-stuffing line verbatim, the quickstart's
`cp -r config.example config`). `tests/test_setup_md.py` and `tests/test_setup_doc.py` pin
SETUP.md against importable constants, including `len(REQUIRED_FILES) + 1 == 6` and the prose
"six files in `config/`" — `decisions.csv` is deliberately NOT a `REQUIRED_FILES` entry and
is documented as machine-written by `judge` rather than as a seventh file to hand-edit, so
that count stays true.

The doctor's check count is prose in four places (`README.md`, `SETUP.md`,
`.vibecodepm/flow.md`, `.vibecodepm/metrics.md`) plus the `tests/test_doctor.py` docstring.
Check 10 (ledger parses) updates all five in the same commit, per the same-commit freshness
rule.

## Definition of done

- Pushed to `derrtaderr/job-radar`, PR opened, not merged.
- A synthetic replay in tests shows each of the six named miss classes caught or flagged.
- A judged posting that returns the next day **under a new id with identical content**
  surfaces with its prior verdict attached rather than as a fresh row.
- A legacy-shaped `state.json` (`jid -> "YYYY-MM-DD"`) still loads and still suppresses.
- `WIRING.md` carries the exact old→new strings for the vault-side daily runner. The vault is
  never edited from this lane.
