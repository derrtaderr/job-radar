# job-radar

A deterministic job-search radar and application workbench: it scrapes fresh postings,
kills the ones your standing rules reject — visibly, quoting the line of the posting that
matched — scores what survives, and hands your Claude Code session a ranked queue. Your
judgment lives in `config/`, as kill rules, a comp floor, scoring weights and a claim
ledger, so the engine never guesses what you want and never calls a model to decide it.
Every conclusion it hands back carries an honesty floor: kills quote their evidence and
stay overrulable, resume claims have to trace to a line you wrote, keyword gaps stay
visible instead of being padded over, and calibration proposals are suppressed by name
when the sample behind them is too small to say anything.

Status: pre-release.

## Quickstart

```bash
git clone <this-repo>
cd job-radar
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

git config core.hooksPath .githooks
# activates the pre-commit privacy check. Without it, nothing stops you from
# committing config/ — your search criteria, salary floor, excluded employers.

cp -r config.example config
# ONLY if config/ doesn't exist yet. Run it over a populated one and cp doesn't
# overwrite your judgment — it NESTS, dropping a second copy at
# config/config.example/ that nothing in this repo reads. Your real files stay
# untouched; delete config/config.example to clean up the junk copy.

.venv/bin/python tools/doctor.py
# nine checks: python, venv, jobspy, typst, config, profile, the privacy hook,
# .gitignore integrity, tracker. Read-only — every fix it prints is yours to run.

# fill in config/ with YOUR profile and rules before the real run

.venv/bin/python radar.py --dry-run    # config loads, pipeline runs, nothing written
.venv/bin/python radar.py              # the real run
```

**`.venv/bin/python tools/demo.py`** — see the whole system run on fictional data before
touching your own config: a full radar pass, a compiled and verified resume/cover letter, and
a calibration report, all against `config.example`'s invented persona, written to `demo-out/`
and nothing sent anywhere. Re-running reuses the same directory; the demo refuses to clear a
directory it didn't create.

Between the copy and the first run, fill in `config/`. Two ways: run **`/setup`** in a
Claude Code session at the repo root, which runs the doctor first and then interviews you
file by file, reading every pattern back in plain English before it writes one — or edit
the six files by hand, with `config.example/README.md` and [SETUP.md](SETUP.md) as the
reference.

A green doctor means your config **loads**, not that it is **right**. The shipped example
loads perfectly and is a fictional data engineer's search.

**[SETUP.md](SETUP.md) is the long-form walkthrough**: prerequisites per OS, every config
field and what the loader does when it's wrong, the tracker format contract, how templates
register, how the archive is laid out, and troubleshooting keyed to the exact strings the
doctor prints.

**[DESIGN.md](DESIGN.md)** is the why: the three subsystems, the boundaries deliberately
kept between them, and the reasoning behind the honesty rules below.

**Run every command from the repo root.** Paths inside `/setup`, `/apply`,
`/add-template`, `/outcome`, `/followup` and every tool under `tools/` are repo-relative
and assume that working directory.

---

## The three subsystems

### 1. Radar — postings in, a ranked queue out

```bash
.venv/bin/python radar.py              # scrape, judge, write today's folder
.venv/bin/python radar.py --dry-run    # smoke test: config loads, zero rows, writes nothing
.venv/bin/python radar.py --check      # re-check the postings your tracker is waiting on
```

`--check` re-checks only the rows in your `tracker_active_sections` that carry a posting
URL — put it anywhere in the row (the Notes cell is the natural spot) and the first
`http(s)` URL it finds is the one used — so you don't spend an application hour on a role
that already closed. It needs `tracker:` set in `config/settings.yaml`. "Unknown" there
means the check learned nothing (bot wall, rate limit, timeout) and is never a soft "dead".

Output lands under `config/settings.yaml`'s `output_dir` (`./radar-out` by default), one
folder per run date. `radar-out/<date>/queue.md` is the ranked table you act on, with the
kills listed underneath it rather than swallowed, and `radar-out/<date>/jd/` holds the full
text of every posting the run judged — survivors and kills alike, so a suspected false kill
is readable off disk instead of taken on faith.

Suppression runs before scoring: a posting you've already seen, a company on your
exclusions list, and a company already in your tracker never reach the rules. Postings
suppressed that way are not recorded as seen, so removing a line from either list brings
that company back on the next run.

### 2. Drafting — a posting in, two verified PDFs out

Needs `typst` on `PATH` (`brew install typst`). PDF verification and the ATS check use
`pypdf`, already pinned in `requirements.txt`.

**`/apply <path-to-a-JD-file-or-pasted-text>`** treats the posting as untrusted data,
extracts the company, role and key requirements, and evaluates fit against your kill rules
and comp floor **before** drafting anything. It then copies the registry's default
templates into `apply-out/<company>-<slug>/`, drafts a resume and cover letter under the
claim gate, compiles both with Typst, verifies each against its page limit and required
contact literals (`tools/verify_pdf.py`), runs a keyword check against the posting
(`tools/ats_check.py`), and hands you the two PDFs, the fit read and a checklist. It never
submits anything.

**`/add-template`** registers a Typst layout you already like, instead of the stock one. It
test-compiles the file before touching `templates/registry.yaml` and again through the
registry afterward, so a registration that looks fine and resolves to nothing can't happen.

### 3. Loop — what happened, and what it should change

**`/outcome`** records an application's fate. On the day you apply it archives the whole
apply-out folder (draft sources, both PDFs, the posting) into `archive_dir`, then moves the
tracker row; every later stage change is logged against that archived copy. Archive first,
then the tracker — a half-failed record stays recoverable that way.

**`/followup`** scans your Active section for rows gone quiet past `followup_after_days`
(10 by default), and for the ones you pick it drafts a nudge built only from what was
actually submitted: the archived resume's own text, the posting, and the dated log. Capped
at two follow-ups per application.

**`tools/calibrate.py`** closes the loop back to `config/`:

```bash
.venv/bin/python tools/calibrate.py <tracker>.md --config config
```

It joins your Closed rows to their archives and proposes changes — proposals only, printed
or written to a file, never applied.

`tools/tracker_cli.py` is the same tracker machinery on the command line (`check`, `add`,
`move`, `touch`, `stale`) if you'd rather not go through a session. Every mutation prints a
unified diff before writing and takes `--dry-run`.

---

## The honesty rules

These are not style preferences. Each one is a place where a system like this could
quietly make something up, and each is closed deliberately.

**No LLM inside the engine.** Not a temporary limitation. The same posting run through the
same config always produces the same kill and the same score, which is what makes rules
tunable, versionable and debuggable. A fuzzy filter would trade that away exactly where a
wrong call — silently dropping a posting you wanted — is hardest to detect.

**Every kill is quoted, and every kill is overrulable.** A kill names the rule that fired
and quotes the line of the posting that matched it, in the queue, with the full posting
text one click away in the day folder. Overruling one is a one-line decision, not an
archaeology project.

**Resume claims trace to your profile, or they come back as a question.** Every bullet
`/apply` drafts has to trace to a line in your own `config/profile.md`. Rephrasing,
reordering and re-emphasizing your real experience for a posting's vocabulary is the work;
inventing a skill, a metric or a responsibility is not. Anything the posting invites that
your profile doesn't support is written into the draft as a visible `[CONFIRM: ...]`
marker, so an unsupported claim is something you answer rather than something that quietly
ships.

**Keyword gaps are reported, never padded.** The ATS check reports missing JD vocabulary as
information. In the tool's own words:

> Gaps are gaps. If the profile genuinely supports one, work it in; if not, it stays visible — never stuffed.

**The follow-up cap counts drafts, not sends.** Two per application, incremented when a
follow-up is drafted. A draft you read and never sent still spent the slot, and a counter
that waits on you to report back drifts low and stops capping anything.

**Calibration suppresses by name.** A proposal needs a minimum N on *both* sides of the
comparison. Every contrast that failed the floor is printed anyway, with its actual counts,
so early in a season the honest report is mostly suppressions rather than confident advice.
Applications whose archive can't be matched unambiguously are named too, with the archives
they collided between, because the join rate is itself a finding.

**Nothing is sent, and nothing is auto-applied. Ever.** Follow-ups are text you copy and
send yourself. Calibration has no `--apply` flag and will not get one. Applying stays your
hand on the button, in `/apply` as everywhere else. The loop commands write to exactly two
places, your tracker and your archive, and every tracker edit prints a unified diff before
it touches the file.

---

## Privacy model

Nothing about a real job search belongs in this repository's history, and the design
assumes you will never push yours.

Gitignored from the first commit: `config/` (queries, kill rules, comp floor, excluded
employers, your claim ledger, seen-job state), `radar-out/` (companies, comp, full posting
text), `apply-out/` (drafts and compiled PDFs carrying your name), `archive/` (everything
that actually went out), `templates/custom/` (layouts that can embed your contact header),
and `.privacy-denylist` itself. Doctor check 8 verifies all six lines are still there,
because deleting one is a silent change with a very loud consequence.

`tools/privacy_guard.py` scans tracked files for email addresses, phone numbers and any
term in your `.privacy-denylist` (copy `.privacy-denylist.example` and fill it in).
Documentation domains and fictional `555-01xx` numbers are exempt, so the shipped example
config passes. It runs as the pre-commit hook once you set `core.hooksPath`, in CI on every
push and pull request, and by hand whenever you want. What it cannot catch: history,
gitignored files, anything you point outside the repo, and any company name or salary
figure you never put in the denylist. SETUP.md section 7 has the full list.

If you plan to commit anything of your own, fork privately.

---

## Notes

**On JobSpy and job-board terms of service.** The scraper is [JobSpy](https://github.com/cullenwatson/JobSpy)
(`python-jobspy`), hitting public job-board endpoints, and the shipped config points at
LinkedIn. LinkedIn's
user agreement restricts automated access, and this repo cannot make that not true. What it
does not do is log in: JobSpy hits public endpoints, and there is nowhere in `config/` to
put LinkedIn credentials because none are used, so the realistic exposure is IP-level rate
limiting and bot walls rather than anything happening to an account. Beyond that, it keeps
the volume in personal-use territory: one person's queries, a handful of
results each, run occasionally rather than on a schedule, with a per-site list you control
in `config/queries.yaml`. Boards rate-limit and show bot walls, and when they do the run
reports it rather than retrying around it. Treat the defaults as a ceiling, not a starting
point, and don't run this on someone else's behalf.

**No typst installed?** The radar half is completely unaffected — the doctor reports it as
a WARN, not a FAIL, and a WARN never changes the exit code. Drafting is what needs it: the
compile step raises `typst binary not found on PATH` before it writes anything, so you get
a clear failure rather than a half-made PDF.

**No jobspy installed?** Mirror image. Drafting and the loop tools work fine; `radar.py`
fails at scrape time naming the missing import.

**Empty queue, everything under "Killed by rule"?** Read the kills before touching the
rules. Each quotes the line that matched, and the full posting sits in the same day folder.
If the quoted line doesn't justify the kill, that's a rule to loosen.

**Running the tests:**

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q
```
