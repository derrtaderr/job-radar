---
name: System map
phase: architect
status: confirmed 2026-09-27 (derived by system-map, walked with the orchestrator; all judgement answers signed by Jason)
read_by: system-map reconcile (/weekly check K); anyone changing where job-radar writes, what it scrapes, or how a missed day is noticed
derived_from: job-radar
---

# System map

Derived from the code by `system-map derive` on 2026-09-27, then confirmed question by question. Every
line is either cited to the code or a signed decision. Convention: a backticked name in section 5 is a
surface reconcile will look for in the code, so commands are written in plain words there.

## 1. The map

- **engine** — 23 files: radar (scrape, rules, score, state, report, tracker, ledger, fingerprint), draft (Typst compile, verify), loop (tracker, outcomes, archive, calibrate) (engine/__init__.py:1)
- **radar.py** — 1 file, the CLI entry point (radar.py:1)
- **tools** — 8 files: doctor, demo, privacy guard, tracker cli, calibrate, ats check, pdf verify (tools/__init__.py:1)
- radar.py → engine (radar.py:6)
- tools → engine (tools/calibrate.py:29)
- tools → tests (tools/demo.py:190)
- tools shells out to `git`, via run (tools/privacy_guard.py:71)
- tests: 48 files, excluded from the map (`--include-tests` to include) (tests/__init__.py:1)
- Decision: the engine also shells out to the Typst binary to compile resumes (engine/draft/compile.py) and reaches job boards over HTTP through the JobSpy library and urllib (engine/radar/scrape.py). Neither is a literal-argument call the scan can name, so both are recorded here by hand.

## 2. Where state lives

- state lives in local files: `path`, written with write_text, and also at engine/loop/archive.py:251 (engine/loop/archive.py:228)
- state lives in local files: `path`, written with write_text (engine/radar/report.py:267)
- state lives in local files: `path`, written with write_text (engine/radar/state.py:47)
- state lives in local files: `args.out`, written with write_text (tools/calibrate.py:83)
- state lives in local files: `jd_path`, written with write_text, and also at tools/demo.py:249, tools/demo.py:276 (tools/demo.py:244)
- Decision: the state is in two places. In the gitignored config directory: the seen-job memory `state.json` (engine/radar/state.py:47) and the decision ledger `decisions.csv`. In the operator's output directory, one folder per day: the daily queue, every JD text, drafted resumes and archived outcomes (engine/radar/report.py:267, engine/loop/archive.py:228). The applications tracker the engine reads and the tracker cli writes lives beside the day folders.
- Decision: the operator's notes repository is git-backed, so day folders and the tracker are backed up. The config directory's rules, weights, queries, profile and exclusions are mirrored to a git-backed location by hand. `state.json` and `decisions.csv` are in neither. Decision (Jason, 2026-09-27): decisions.csv joins the operator's git-backed mirror of the config directory, copied after every judgement pass by the operator's daily routine. state.json stays unmirrored: losing it re-surfaces every seen posting once, which is recoverable.

## 3. Doors and keys

- Unknown: no credential-shaped environment variable was found, so either this system holds no key or a key is arriving by a route the scan cannot see
- Decision: there are no keys. Job boards are scraped as an anonymous visitor; Typst is a local binary; the tracker and the vault are local files. The doors are the operator's shell and the config directory, which holds personal judgement and never leaves the machine.
- Decision: there is no HTTP route and no authorization check, and that is correct for a local CLI.
- Decision: no key or personal datum is committed; the privacy guard refuses commits carrying emails, phone numbers or home paths (tools/privacy_guard.py:1).

## 4. What bills per use

- `git` is run as a subprocess, so whatever it reaches is metered by that system's limits rather than billed here (tools/privacy_guard.py:71)
- Decision: nothing bills. Scraping is bounded by the boards' bot walls and rate limits; a blocked fetch resolves to an unknown liveness, never to closed. There is no spend and no cap to set. The one metered thing is the operator's attention: the judgement pass reads the top survivors' JDs every morning.

## 5. How you find out it broke

- Unknown: nothing was found that records a failure, which means a failure leaves no trace this scan can see
- Decision: the radar does not push. Its surfaces are the day folder (present or absent), the one-line "nothing new today", and the doctor's ten checks. The reader that cannot go quiet is the daily brief, which runs the radar every morning and reads the queue; a morning with no day folder and no "nothing new" line is the alarm. Decision (Jason, 2026-09-27): a missed morning is noticed the same day by the daily brief; no push is wanted.

## 6. Blast radius per piece

- **engine** — 2 other pieces import it (radar.py, tools), so breaking it breaks those too (radar.py:6)
- **radar.py** — nothing in this repo imports it, so breaking it breaks only itself, unless it is an entry point (radar.py:1)
- **tools** — nothing in this repo imports it, so breaking it breaks only itself, unless it is an entry point (tools/__init__.py:1)
- Decision: radar.py is the entry point, so breaking it breaks every morning; breaking tools breaks the doctor, the demo, the tracker cli and the guard, but not the radar run.

## What the scan could not see

- `NOTED` `DYNAMIC_IMPORT_MODULE` — importlib.import_module is called with a computed name, so the edge it creates cannot be read from the text (tools/doctor.py:76)
- Known and accepted: the Typst shell-out and the JobSpy and urllib network calls use computed arguments, so sections 1 and 4 name them by hand.
