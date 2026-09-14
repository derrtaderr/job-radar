# Setting up job-radar

The README's quickstart is the short version. This is the long one: every
prerequisite, every config field and what the loader does when it's wrong, the tracker
format contract, how templates register, how the archive is laid out, what the doctor's
failures mean, and what the privacy machinery does and does not catch.

Read it once on your first setup, then come back to the troubleshooting section when
something says FAIL.

---

## 1. Prerequisites

**Python 3.11 or newer.** The doctor's first check enforces it (`MIN_PYTHON = (3, 11)` in
`tools/doctor.py`). Below that it prints `FAIL python version` and tells you to upgrade.

**git.** Used for the clone and, more importantly, for the pre-commit privacy hook.

**typst**, but only for the drafting half. The radar never touches it.

```bash
# macOS
brew install typst
```

On Linux, typst ships prebuilt binaries on its GitHub releases page, and several distros
package it (snap, AUR, nixpkgs); `cargo install --locked typst-cli` also works if you have
a Rust toolchain. Any of them is fine as long as `typst` ends up on your `PATH` — that is
the only thing this repo checks.

Everything else is Python packages:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt        # pyyaml, pypdf, python-jobspy
.venv/bin/pip install -r requirements-dev.txt    # the above plus pytest
```

`requirements-dev.txt` includes `requirements.txt`, so install just that one if you intend
to run the test suite.

---

## 2. First run, in order

This is the README's quickstart, one step at a time. Same order, and the order matters in
one place: **run the doctor before you author judgment into config, not after.** Copying
the example config first is fine and expected — what wastes an hour is writing your own
kill rules, comp floor and claim ledger on a machine whose virtualenv or Python version
can't load them.

```bash
git clone <this-repo>
cd job-radar
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

git config core.hooksPath .githooks      # activates the pre-commit privacy check
cp -r config.example config              # ONLY if config/ doesn't exist yet
.venv/bin/python tools/doctor.py         # fix every FAIL before you start authoring
```

**That `cp -r` only ever runs when `config/` doesn't exist.** Run it over a populated
`config/` and nothing gets destroyed — `cp -r` NESTS instead, dropping a second copy of the
example at `config/config.example/` that nothing in this repo reads. Your kill rules, comp
floor, and claim ledger stay exactly as they were; the nested copy is inert clutter, and
`rm -rf config/config.example` clears it.

Straight after the copy, the doctor should carry no FAIL — a tracker SKIP is expected, and
so is a WARN on typst or jobspy if you skipped one of those (paths will be yours):

<!-- doctor-after-copy -->

```
OK   python version: python 3.14.6
OK   venv + required packages: .venv/ present; pypdf, yaml importable
OK   jobspy: jobspy importable
OK   typst: typst on PATH
OK   config: config loads from <repo>/config
OK   profile: <repo>/config/profile.md has the required shape
OK   privacy hook: core.hooksPath is .githooks
OK   gitignore integrity: <repo>/.gitignore has all 6 required lines
SKIP tracker: no tracker: configured in settings.yaml — nothing to check
```

Nine checks, always all nine. The doctor never stops at the first problem, because a
half-set-up machine usually has more than one, and finding them one run at a time is nine
trips instead of one. It also never writes anything — including the git config it reads in
check 7. Every fix it prints is a command you run.

Now bring your own judgment in. Either run `/setup` in a Claude Code session at the repo
root (it runs the doctor first, then interviews you file by file, reading every pattern
back in plain English before writing it), or edit the six files in `config/` by hand using
section 3 below. Then re-run the doctor until it is green again, and take the first run:

```bash
.venv/bin/python radar.py --dry-run     # loads config, runs the pipeline on zero rows, writes nothing
.venv/bin/python radar.py               # the real thing
```

A green doctor means your config **loads**, not that it is **right**. The example config
loads perfectly and is a fictional data engineer's search, which is exactly why the
authoring step above is not optional.

---

## 3. The config files, field by field

All six live in `config/`. Paths inside `settings.yaml` resolve relative to `config/`'s
parent — the repo root — not to `config/` itself, so `./radar-out` means
`<repo>/radar-out`.

Every loader failure raises a `ConfigError` that names the file and the key. Three
validation behaviors are worth knowing up front, because they catch the typos YAML is
happy to accept:

- **Integers must be integers.** `comp_floor: yes` parses as the boolean `True`, and
  `True` passes a naive `isinstance(x, int)` check, so it would silently become a floor of
  1. Every int key is checked for bool and float too, and rejected by name.
- **Lists must be lists.** `searches: Data Engineer` parses as a string, and a string is
  iterable, so the engine would run one query per letter. A non-list, or a list with a
  non-string in it, is rejected by name.
- **Regexes are compiled at load.** A pattern that won't compile fails the whole load with
  the file, the key, and the regex error, rather than failing quietly on posting number
  forty. Every pattern in every file is compiled case-insensitive.

### `queries.yaml` — what to search for

| Key | Type | Behavior |
|---|---|---|
| `searches` | list of strings, non-empty | One JobSpy query per entry. Every site runs every query. |
| `sites` | list of strings, non-empty | Passed straight to JobSpy, which supports `linkedin`, `indeed`, `zip_recruiter`, `glassdoor`, `google`, `bayt`, `naukri`, `bdjobs`. `[linkedin]` is the shipped default and the one this repo is tested against. |
| `location` | string, required | Passed to the board as-is. A country, a metro, or "remote". |
| `results_per_query` | int | Per query, per site. |
| `hours_old` | int | Freshness ceiling handed to the board. 336 (14 days) is the shipped default. |
| `title_keep` | regex | A title must match to survive. |
| `title_drop` | regex | A title matching this is dropped even if `title_keep` matched. |

Title filtering happens before scoring and before the kill rules, and a dropped title is
not written to a JD file — it never entered the run. Kills are the visible ones; title
drops are the quiet ones, so keep `title_drop` narrow.

### `rules.yaml` — the judgment transfer

| Key | Type | Behavior |
|---|---|---|
| `comp_floor` | int, required | A posting whose posted yearly max is below this is killed as `comp-below-floor`. With no structured comp, the body is scanned for a stated range near salary language; below the floor kills as `comp-below-floor-stated`. |
| `commute_locations` | regex or empty | Non-remote postings whose location matches still pass. Empty (or absent) means remote-only. |
| `rules` | list of `{name, reason, pattern}` | Your named kill rules. All three keys are required on every rule. |

Every kill rule is matched against the posting body, and a match records the rule's name
plus the matched line as quoted evidence.

**The `reason` field never renders in the queue.** The report prints the rule name and the
evidence line only. `reason` lives in `rules.yaml` next to the pattern, which is where you
trace a kill's why — write it for yourself six months from now, not for the queue.

Two kill checks are built into the engine rather than configured: the comp floor above,
and a location rule that kills a non-remote posting outside `commute_locations`. The
location rule reads the structured location first, falls back to "based in / office in /
on-site in <City>" in the body, and lets affirmative remote language in the posting
override it — unless the body also carries in-office cadence language ("3 days a week in
the office"), which defeats the override.

### `weights.yaml` — the scoring model

| Key | Type | Behavior |
|---|---|---|
| `title_tiers` | list of `{pattern, points}` | First match wins, top to bottom. Order them most specific first. |
| `default_title_pts` | int | Points for a title that matched no tier. |
| `comp_target` / `target_comp_pts` / `floor_comp_pts` / `unlisted_comp_pts` | int | Comp scoring: at or above target, above floor, and no comp posted at all. |
| `fresh_days` / `fresh_pts` / `week_pts` / `old_pts` | int | Freshness bands. |
| `remote_pts` | int | Bonus for a remote posting. |
| `seniority_pattern` / `seniority_pts` | regex / int | Bonus when the title matches. |

Every key here is required except `title_tiers`, which may be absent or empty — every title
then scores `default_title_pts`. Every points value must be a bare integer.

### `settings.yaml` — paths, tracker, windows

| Key | Required | Behavior |
|---|---|---|
| `output_dir` | yes | Day folders land here. Gitignored as `radar-out/` by default. |
| `state_file` | yes | Seen-job memory. Keep it inside `config/`, which is gitignored. |
| `tracker` | no (defaults to `null`) | Path to your markdown tracker. Absent, `null`, or empty all mean no suppression and no `--check`. |
| `tracker_active_sections` | yes (may be empty) | Which tracker sections count as "in play". Matched against lowercased section names. |
| `closed_window_days` | yes | A company whose Closed row is dated inside this window stays suppressed. |
| `followup_after_days` | no, default 10 | An Active row this many days quiet is flagged stale. |
| `archive_dir` | no, default `./archive` | Where applied applications are archived. |

A `tracker:` path that points at a file which isn't there does **not** stop a run. It
prints a loud warning and suppresses nothing that run:

```
radar: WARNING — tracker configured as <path> but no file is there, so NOTHING is being
suppressed this run (fix `tracker:` in settings.yaml, or set it to null if you don't keep one)
```

That warning exists because one typo would otherwise cost every future run its suppression
with no symptom at all.

### `exclusions.txt` — companies you never want to see

One per line. Blank lines and `#` comments are ignored. Matching is case-insensitive
substring, so `Northwind` covers `Northwind Analytics, Inc.` An excluded posting is never
scored and never recorded as seen, so deleting a line here brings that company back on the
next run.

`exclusions.txt` is suppression. `.privacy-denylist` (section 7) is privacy. They are
different files with different jobs; do not merge them.

### `profile.md` — the claim ledger

The one config file the drafting side reads, and the only one that is about you rather than
about the search. It needs:

- frontmatter with `name`, `email`, `phone`, `location`, `links`, each with a value;
- the sections `## Summary`, `## Experience`, `## Skills`, `## Education`,
  `## Evidence notes`;
- this sentence, verbatim, anywhere in the file:

  > This file is the CLAIM LEDGER. The drafter may only write resume claims that trace to a line here.

Doctor check 6 validates all three. If the file doesn't open with a `---` fence, the check
reports only that — the per-key checks can't run on a file whose frontmatter never parses.

Write it longer than any one resume needs. Tailoring works by selecting from a deep ledger;
a ledger trimmed to resume length hands the drafter the same page every time.

---

## 4. The tracker format contract

The tracker is a plain markdown file you own and can hand-edit at any time. Four sections,
each holding one table:

```markdown
## Active

| Company | Role | Source | Stage | Comp band | Last touch | Next step | Notes |
|---|---|---|---|---|---|---|---|

## Drafted but not applied

| Company | Role | Source | Comp band | Resume | Next step | Notes |
|---|---|---|---|---|---|---|

## Research (JD filed, no work started)

| Company | Role | Comp band | Lean | Notes |
|---|---|---|---|---|

## Closed

| Company | Role | Date closed | Outcome | Reason | Carry-forward lesson |
|---|---|---|---|---|---|
```

**Where this file goes.** It holds real companies and real comp bands, so it belongs inside
`config/` (gitignored) or outside the repo entirely — never at the repo root under a name git
will track. `settings.yaml`'s `tracker:` key points at wherever you put it.

**Where the posting URL goes.** Put it in the row's Notes cell — `radar.py --check` scans the
whole row for the first `http(s)` URL it finds, so any cell works, but Notes is the one built
for free text. A row with no URL is skipped by `--check`, not flagged, since there is nothing
to re-check.

What the validator (`engine/loop/tracker_schema.py`, run by `tools/tracker_cli.py check`
and doctor check 9) actually enforces:

- **`## Active` and `## Closed` must exist.** The other two are optional.
- **Required columns.** Active needs `Company`, `Role`, `Last touch`. Closed needs
  `Company`, `Role`, `Date closed`, `Outcome`. The other two sections' columns are expected
  shape rather than requirements. Extra columns are fine everywhere **except before
  `Date closed` in Closed**: the radar's closed-window suppression reads that date from the
  third data column **by position**, not by header name, so inserting a column ahead of it
  silently moves the read onto the wrong cell — and the validator stays green, because the
  header it requires is still present.
- **Cell count matches the header count**, per row, reported with a line number.
- **`Last touch` and `Date closed` carry ISO dates** (`2026-09-13`) whenever non-empty.
- **No duplicate Company+Role within Active or Drafted but not applied.** Closed and
  Research allow repeats on purpose — reapplying to the same role months later is a real
  thing, and flagging it would be a false positive.

**Headings: two different matchers, and this is the trap.** The *validator* strips a
trailing parenthetical, so `## Research (JD filed, no work started)` checks as the
`research` section. **The radar's suppression readers do not strip anything — they match
the full lowercased heading text.** So `## Active (in play)` with
`tracker_active_sections: [active]` suppresses **nothing**, and the doctor stays green
while it does, because the validator is perfectly happy with that heading. Same rule on the
other side: the closed-window reader matches the literal heading `## Closed`, so
`## Closed (done)` is never read, exactly like `## Archive` is never read. Keep the four
headings spelled as the template above spells them, and put annotations in a cell rather
than in a heading.

**Two readers, two different sets of sections.** `radar.py --check` re-checks only the
postings in your `tracker_active_sections`; it never reads Closed. A normal `radar.py` run
suppresses companies in those same active sections, plus anyone whose `## Closed` row
carries a close date inside `closed_window_days`. A Closed row with no parseable date
suppresses nothing, deliberately — an unknown close date must never silently hide fresh
postings.

Check yours any time:

```bash
.venv/bin/python tools/tracker_cli.py check <tracker>.md
# tracker: OK (0 rows across 4 sections)
```

`tracker_cli.py` also does the edits `/outcome` and `/followup` make (`add`, `move`,
`touch`) and the stale scan (`stale`). Every mutation prints a unified diff of the change
before writing, writes atomically, and takes `--dry-run` to print the diff and touch
nothing.

---

## 5. How templates register

`templates/registry.yaml` is the lookup table `/apply` resolves a template name through:

```yaml
default_resume: stock-resume
default_cover: stock-cover
templates:
  - {name: stock-resume, source: templates/resume.typ, kind: resume, page_limit: 2}
  - {name: stock-cover,  source: templates/cover.typ,  kind: cover,  page_limit: 1}
```

`source` is repo-relative. `kind` is `resume` or `cover`. `page_limit` must be a bare
integer, and it is what `tools/verify_pdf.py` gates the compiled PDF against. A missing
file, a malformed entry, or a lookup for an unknown name raises a `RegistryError` naming
the entry and listing the names that do exist.

To register your own layout, use `/add-template`. It interviews you, copies the file into
`templates/custom/`, test-compiles it **before** touching the registry, appends the entry,
and then compiles again through the registry to prove the entry itself is right.

One thing to know before you commit anything: **`templates/registry.yaml` is tracked and
`templates/custom/` is gitignored.** A custom registration is the one place in this repo
where a tracked file points at a source git will never carry. Committing such an entry
breaks every fresh clone, because the registry loader raises on a source that doesn't
exist. Keep the registry edit local, the same way `config/` stays local, unless the
template itself is personal-data-free and tracked.

---

## 6. How the archive works

`/outcome` archives an application on the day you apply, before it moves the tracker row.
The archive is a mirror of the apply-out folder plus one file:

```
<archive_dir>/<company>-<slug>/
├── jd.md            the posting, as it was when you applied
├── resume.typ       the draft sources
├── cover.typ
├── resume.pdf       the compiled documents that actually went out
├── cover.pdf
└── outcome.md       written by the archiver
```

`outcome.md` is a small frontmatter block plus a dated log:

```markdown
---
company: Acme Example
role: Data Engineer
applied: 2026-09-13
followups: 0
---

## Log
- 2026-09-13: applied
```

Properties worth relying on:

- **All or nothing.** Everything is staged into a temporary directory inside `archive_dir`
  and renamed into place only after the last file lands. A failure partway through leaves
  no slug directory, so a retry starts clean instead of meeting a husk it has to refuse.
- **It never clobbers.** An existing slug directory is refused by name.
- **It refuses to invent.** If the apply-out folder is gone, archiving fails rather than
  rebuilding a record out of materials that may not be what was submitted. Record the
  outcome without an archive instead.
- **`followups` is the cap's counter**, capped at 2. It is incremented when a follow-up is
  **drafted**, not when one is sent.
- Later stage changes append a dated line to `## Log` without disturbing anything else in
  the file.

The archive is also what `tools/calibrate.py` joins your Closed tracker rows against. Which
is why the archive being faithful matters: calibration reads what was actually sent.

---

## 7. Keeping your data yours

**Clone privately if you intend to commit anything.** Nothing in this repo needs you to
push, and the design assumes you won't push your judgment. If you do want your own commits
(a tweaked template, a note to yourself), make the remote a private fork.

**What is gitignored, and why:**

| Path | Holds |
|---|---|
| `config/` | your queries, kill rules, comp floor, excluded employers, claim ledger, seen-job state |
| `radar-out/` | day folders: companies, comp, and the full text of every posting a run touched |
| `apply-out/` | per-application drafts and compiled PDFs, with your name and contact details in them |
| `archive/` | everything that actually went out, plus the outcome log |
| `templates/custom/` | custom templates, which can embed your contact header |
| `.privacy-denylist` | the terms you never want appearing in a tracked file, which is itself a list of personal facts |

Doctor check 8 verifies all six lines are still in `.gitignore`, because deleting one is a
silent change with a very loud consequence.

**The privacy guard** (`tools/privacy_guard.py`) scans **tracked files only** for three
things: email addresses, phone numbers, and any term in your `.privacy-denylist`. RFC 2606
documentation domains (`example.com`, `.org`, `.net`) and NANP fictional numbers
(`555-01xx`) are exempt, so the shipped example config passes. It runs in three places: as
the pre-commit hook (once you set `core.hooksPath`), in CI on every push and pull request,
and by hand:

```bash
.venv/bin/python tools/privacy_guard.py    # silent + exit 0 means clean
```

Copy `.privacy-denylist.example` to `.privacy-denylist` and list your name, employers,
clients, and city, one per line, case-insensitive substring.

One assumption in the hook worth knowing: `.githooks/pre-commit` execs
`.venv/bin/python tools/privacy_guard.py`, that path literally. If your virtualenv lives
somewhere else or your environment manager puts the interpreter under a different name,
edit that one line in the hook — otherwise every commit fails on a missing interpreter,
which looks nothing like a privacy problem.

**What it does not catch**, stated plainly so you don't over-trust it:

- Anything already committed. It scans the current tracked tree, not history.
- Untracked and gitignored files. That is the point, but it means a file you later `git add
  -f` is only caught on the commit that adds it.
- A company name, a job title, or a salary figure that isn't in your denylist. The guard
  has no idea what is sensitive to you beyond what you told it.
- Anything outside the repo. If you point `output_dir` or `archive_dir` somewhere else on
  your disk, keeping that location private is entirely yours.
- The hook itself, if `core.hooksPath` is unset. Check 7 exists for exactly that reason.

---

## 8. Troubleshooting

Every string below is what the tool actually prints.

### The doctor

**`FAIL python version: python 3.10.x`** → install Python 3.11 or newer and rebuild the
virtualenv against it.

**`FAIL venv + required packages: no .venv/ found at <path>`** →
`python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt`

**`FAIL venv + required packages: .venv/ present but not importable: pypdf, yaml`** → same
pip line. Usually means the venv was created but never installed into, or you are running
the doctor with a different interpreter than the one you installed into. Run it as
`.venv/bin/python tools/doctor.py`.

**`WARN jobspy: jobspy not importable — the radar (scrape) needs it, drafting/loop tools
don't`** → `pip install python-jobspy`. A WARN never blocks and never affects the exit
code. Without jobspy the drafting and loop halves work fine; `radar.py` itself will fail at
scrape time with `radar: scrape module not yet available ... underlying import error`.

**`WARN typst: typst not on PATH — drafting (resume/cover-letter compile) needs it`** →
`brew install typst` (or see section 1). The radar is unaffected. If you try to draft
anyway, the compile step raises ``typst binary not found on PATH — install it with `brew
install typst` `` before it writes a PDF.

**`FAIL config: no config at <dir> — copy config.example/ to config/ and edit it`** →
`cp -r config.example config`, and only when `config/` doesn't already exist. Any other
config FAIL is the loader naming the file and key it rejected — fix that line and re-run.

**`SKIP profile: config didn't load — see the 'config' check above`** → not a failure. Two
checks need a loaded config to have anything to check; they skip rather than pile a second
error on top of the first.

**`FAIL profile: profile.md must open with a '---' frontmatter fence`** → the file's first
line must be `---`. A comment or a heading above it breaks the parse, and this is the one
placement mistake the schema cannot explain any more specifically.

**`FAIL profile: profile.md frontmatter block is never closed with '---'`** → the file
opens with a fence but never closes it, so nothing below can be parsed. Add the closing
`---` line under the last key.

**`FAIL profile: profile.md frontmatter missing keys: [...]`** /
**`profile.md missing sections: [...]`** / **`profile.md must state the claim-ledger rule
verbatim`** → see section 3's profile.md fields. The third one means the sentence is
missing, paraphrased, or re-punctuated; it has to match exactly.

**`FAIL profile: profile.md frontmatter key 'phone' has no value`** → the key is present
with nothing after the colon. An empty key is the same failure as a missing one from the
drafter's side: it has nothing to put in the contact line, and `tools/verify_pdf.py` gates
on those literals appearing in the compiled PDF.

**`FAIL privacy hook: core.hooksPath is not set`** → `git config core.hooksPath .githooks`.
It is per-clone, so a second clone on another machine needs it again. If it reports a
different path than `.githooks`, you (or another tool) pointed hooks elsewhere.

**`FAIL gitignore integrity: <path> is missing: config/, apply-out/`** → add the named
lines back. Do this before your next commit, not after.

**`SKIP tracker: no tracker: configured in settings.yaml — nothing to check`** → expected
if you don't keep a tracker. Note that a tracker you wrote but never wired (`tracker:`
still `null`) produces this same SKIP, which looks identical to a clean run. Writing the
file and leaving the key null wires nothing.

**`FAIL tracker: tracker configured at <path> but the file does not exist`** → fix the path
in `settings.yaml` or move the file back. Anything else the tracker check reports is a
contract violation from section 4, quoted with its line number.

**`OK   tracker: <path> matches the tracker format contract`** → clean; nothing to fix.

### The radar

**`radar: dry run — config OK (3 queries, 3 kill rules), 0 rows in, 0 queued, 0 killed,
nothing written`** → success. Zero rows is what `--dry-run` means, not a broken scrape.

**`radar: SCRAPE RETURNED 0 ROWS — treat as a broken scrape, not a quiet day`** → exit 1,
and the seen-job state is deliberately left untouched so a bad run can't poison the next
one. Usually a rate limit or a bot wall. Wait, then re-run.

**``radar: --check needs a tracker — set `tracker:` in settings.yaml to a markdown file of
your applications``** → exit 2. `--check` has nothing to re-check without a tracker.

**`UNKNOWN means the check learned nothing (bot wall, rate limit, timeout). Treat as still
open and verify by hand`** → exactly what it says. Unknown is not a soft "dead", and
treating it as one would talk you out of a role that is still open.

**Your queue is empty and everything is under "Killed by rule"** → read the kills. Each one
names the rule and quotes the line that matched, and the full posting is in the same day
folder under `jd/`. If the quoted line doesn't justify the kill, that is a rule to loosen,
not a queue to distrust.

**A posting you expected never appears at all, not even as a kill** → it was filtered
before judging: already seen (it's in `state_file` from an earlier run), an excluded
company, a company already in your tracker, or a title your `title_keep`/`title_drop` pair
rejected. Only the first of those is time-based; the rest are config, and all four are
silent by design.
