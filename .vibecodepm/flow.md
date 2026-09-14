---
name: job-radar flow map
read_by: the Phase 4 ship-check / stranger-walk audit before any release or visibility decision, and any session that adds a CLI verb, a config field, or a new failure state
milestone: Phase 4 (offline demo + ship-check contract files)
status: current — matches the build at lane/phase-4
date: 2026-09-13
supersedes: none — first flow map for this repo
---

# Flow map — job-radar

What a first-time user does, what they see, and what happens when something is missing or
wrong. The ship-check walks the build against this document, so a gap between this file and
the build is a finding rather than a detail.

Some states below are rough on purpose, and this file says so where that's true rather than
describing a smoother system than the one that ships. Where a recovery path is "read the
error, fix the one file it names," that IS the design (see README's honesty rules and the
config/registry loaders' "always names the offending file/key/rule" standard) — it is not a
placeholder for a nicer flow that didn't get built.

## Who walks this

Two different people, and the flow forks early between them.

**A stranger evaluating the repo.** Cloned it, has five minutes, wants to see the whole
system do something real before deciding whether to spend more time on it. Never had a
real job search in this tool. `tools/demo.py` exists for exactly this person —
see "The demo detour" below.

**The tool's actual user, mid-search.** Has `config/` filled in with their own profile and
judgment, keeps a tracker, and returns to this tool most days. The happy path below is
theirs.

## Entry point

```
git clone <this-repo>
cd job-radar
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
git config core.hooksPath .githooks
.venv/bin/python tools/doctor.py
```

The doctor runs nine checks (python version, venv + packages, jobspy, typst, config,
profile, the privacy hook, `.gitignore` integrity, tracker) and is read-only — every fix it
prints is a command the human runs, never one the doctor runs for them. Run it right after
the clone, before the `git config core.hooksPath` and `cp -r config.example config` steps
above, and a fresh clone gets two FAILs (config, privacy hook) with everything else either
passing or SKIPping behind them; both FAILs are expected, not a broken install.

### The demo detour

Before (or instead of) filling in `config/`, `.venv/bin/python tools/demo.py` runs the
whole system — radar, drafting, loop — on `config.example`'s fictional persona, into
`demo-out/`, touching nothing real. It never reads `config/`, never writes state, and never
sends anything. This is the path a stranger with five minutes actually takes; the happy
path below is what they'd be signing up for if they kept going with their own search.

## Happy path

1. **Setup.** `cp -r config.example config`, then either run `/setup` in a Claude Code
   session (interviews file by file, reads every pattern back before writing it) or hand-edit
   the six files with `config.example/README.md` and `SETUP.md` as reference. Re-run the
   doctor until it's green. A green doctor means the config **loads**, not that it is
   **right** — nothing checks whether the comp floor or kill rules reflect what the human
   actually wants.
2. **Daily radar.** `.venv/bin/python radar.py` scrapes, judges every posting against
   `config/`'s rules, and writes `radar-out/<date>/queue.md` — a ranked table with kills
   shown underneath it, never swallowed, each quoting the line that matched. `--check`
   re-checks tracked postings for liveness instead of scraping fresh ones.
3. **Apply.** `/apply <JD>` evaluates fit against kill rules and comp floor BEFORE drafting
   anything, then drafts a resume and cover letter under the claim gate (every bullet traces
   to `config/profile.md` or comes back as `[CONFIRM: ...]`), compiles both with Typst,
   verifies each PDF (`tools/verify_pdf.py`), and runs a keyword check against the posting
   (`tools/ats_check.py`). Never submits anything.
4. **Outcome.** `/outcome` archives the whole `apply-out/` folder into `archive_dir` the day
   the application goes out, then moves the tracker row through Active to Closed as the
   application resolves. `/followup` drafts nudges for quiet Active rows, capped at two per
   application.
5. **Weekly calibrate.** `tools/calibrate.py <tracker>.md --config config` joins Closed rows
   to their archives and proposes rule/weight changes — a report a human reads and applies
   by hand. No `--apply` flag exists and none will.

## States and recovery

### No config

`load_config` refuses to guess: `ConfigError` reads exactly `no config at <dir> — copy
config.example/ to config/ and edit it (see config.example/README.md)`. The doctor's config
check surfaces the same condition as `FAIL config: no config at <dir> — copy config.example/
to config/ and edit it`, and every OTHER doctor check that needs a loaded config (profile,
tracker) SKIPs behind it rather than piling a second, confusing error on top of the first. Fix is
always `cp -r config.example config`, only when `config/` doesn't already exist — running it
over a populated `config/` doesn't destroy anything, it NESTS: you end up with a junk copy at
`config/config.example/` that nothing in this repo reads, while your real files stay exactly
as they were. `rm -rf config/config.example` clears it. That's still why the doctor never
runs this for you — a confusing junk copy is not a fix.

### No typst

Named, not silent, and scoped to exactly the half of the system that needs it. The doctor
reports `WARN typst: typst not on PATH — drafting (resume/cover-letter compile) needs it`
with fix `brew install typst`; a WARN never flips the doctor's exit code. The radar and loop
halves are completely unaffected. If drafting is attempted anyway, `compile_pdf` raises
`typst binary not found on PATH — install it with \`brew install typst\`` before it writes
a single byte — a clear failure at the first line of the drafting chain, not a half-written
PDF three steps in. `tools/demo.py` mirrors this exactly: it checks `shutil.which("typst")`
itself, prints a named note, and skips only the drafting branch when typst is absent.

### Invalid tracker

Three distinct conditions, each surfaced differently, because collapsing them would make a
config typo look identical to "I don't keep a tracker":

- **Never configured** (`tracker: null`) — `--check` prints `radar: --check needs a
  tracker — set \`tracker:\` in settings.yaml to a markdown file of your applications` and
  exits 2. The doctor SKIPs its tracker check the same way, which is expected and looks
  identical to the case below — a known rough edge (SETUP.md names it directly rather than
  smoothing it over).
- **Configured but missing on disk** — a normal radar run WARNs (`radar: WARNING — tracker
  configured as <path> but no file is there, so NOTHING is being suppressed this run`) and
  keeps going, because a missing tracker must not take the whole radar down. `--check`
  instead refuses outright (`radar: --check needs the tracker, but no file is at <path>`,
  exit 2), because liveness-checking has nothing to check.
- **Present but malformed** — `tracker_check()` returns a list of violations, each naming
  its own row and section (`missing required section: ## <name>`, and similar
  section/column/duplicate-row messages), rather than a single generic parse failure. The
  CLI (`tools/tracker_cli.py check`) prints every one; nothing downstream (`/outcome`,
  `/followup`, calibration) runs against a tracker that fails this check.

### Cap states

`/followup`'s per-application cap is two, enforced by `bump_followup` before anything is
written: a third bump raises `FollowupCapError` reading `followup cap (2) reached for
'<slug>' — cannot bump past 2`, and the file is left untouched. The cap counts DRAFTS, not
sends — a follow-up drafted and never sent still spent the slot, which is a deliberate
choice (a counter waiting on "did you actually send it" drifts low and stops capping
anything) rather than an oversight.

### Ambiguous joins

Calibration's `join_archives` can fail to pair a Closed tracker row to exactly one archive
in two ways, and both are named in the report rather than silently dropped or silently
guessed: an **unjoined** row (no archive matched at all) counts against the join rate in the
summary, and an **ambiguous** row (more than one archive matched — most often a genuine
reapplication archived twice) is reported by name with every candidate slug it could not
choose between, so a human resolves it by renaming one side rather than the tool picking
one for them. A report built on 4 of 20 applications reads very differently from one built
on 18 of 20, which is why both counts are always in the summary, never just the join count
that succeeded.
