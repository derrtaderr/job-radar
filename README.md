# job-radar

Deterministic job-search radar: scrape fresh postings, kill the ones your standing
rules reject (visibly, with the matched line quoted), score the rest, and hand your
Claude Code session a ranked queue. Your judgment lives in `config/` — the engine
never guesses.

Status: pre-release. Not yet accepting issues.

## Quickstart

```bash
git clone <this-repo>
cd job-radar
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

cp -r config.example config
# edit every file in config/ — your target titles, kill rules, comp floor,
# scoring weights, output paths, excluded companies (see config.example/README.md)

git config core.hooksPath .githooks
# required: activates the pre-commit privacy check. Without it, nothing stops
# you from accidentally committing config/ — your search criteria, salary
# floor, excluded employers — into a shared repo.

python radar.py
# (or .venv/bin/python radar.py if .venv isn't already on your PATH)
```

## Running it

Three ways to invoke `radar.py`:

- **`python radar.py`** — a normal run. Scrapes every query in `config/queries.yaml`,
  applies your kill rules and scoring, and writes today's day folder.
- **`python radar.py --check`** — re-checks the postings your tracker says you're
  waiting on, so you don't spend an application hour on a role that already
  closed. Requires `tracker:` set in `config/settings.yaml`. Closed-application
  suppression only reads a section literally headed `## Closed` — a
  differently-named section (e.g. `## Archive`) is never read.
- **`python radar.py --dry-run`** — loads the config and runs the pipeline on
  zero rows, writing nothing. The smoke test: proves your config is valid
  without touching the network or the filesystem.

Output lands under `config/settings.yaml`'s `output_dir` (`./radar-out` by
default), one folder per run date: `radar-out/2026-09-13/queue.md` is the
ranked table you act on, and `radar-out/2026-09-13/jd/` holds the full text of
every posting the run touched — survivors and kills alike, so a kill is always
checkable, never just taken on faith.

## Your judgment lives in config/

The engine (`engine/`) has no opinions of its own. Every decision that makes
this *your* search rather than a generic one — which titles to keep, which
companies to never see again, what counts as a comp floor, how freshness and
seniority get weighted — lives in `config/`, which is gitignored on purpose
and never gets written back into the repo. Clone this repo and you get the
machinery; `config/` is where you tell it what you're actually looking for.

## Drafting

Turning a posting into a tailored resume and cover letter is a separate step from the
radar run, and it depends on a couple of things beyond the Python environment.

**Prerequisites:**

```bash
brew install typst
```

PDF verification and ATS checking use `pypdf`, which is already pinned in
`requirements.txt` — no separate install.

**The flow (`/apply <path-to-a-JD-file-or-pasted-text>`):** the command treats the posting
as untrusted data, extracts the company, role, and key requirements, and evaluates fit
against your kill rules and comp floor in `config/rules.yaml` before drafting anything. It
then copies the registry's default templates into `apply-out/<company>-<slug>/`, drafts a
resume and cover letter under a claim gate, compiles both to PDF with Typst, verifies each
against its page limit and required contact literals, runs an ATS keyword check against the
posting, and hands you the two PDFs, the fit read, and a checklist — never submitting
anything itself.

**The claim gate:** every bullet has to trace back to a line in your own `config/profile.md`.
Rephrasing, reordering, and re-emphasizing your real experience for a posting's vocabulary is
the work; inventing a skill, a metric, or a responsibility the profile doesn't support is not.
Anything a posting invites that the profile doesn't back gets written into the draft as a
visible `[CONFIRM: ...]` marker instead, so an unsupported claim is something you answer, not
something that quietly ships.

**No stuffing:** the ATS check reports keyword gaps as information, never as something to fix
by padding. In its own words:

> Gaps are gaps. If the profile genuinely supports one, work it in; if not, it stays visible — never stuffed.

**`apply-out/` is gitignored on purpose.** Everything a drafting run produces — the posting
text, draft `.typ` sources, and compiled PDFs — holds real personal data and must never land
in a shared repo.

Have a resume layout you already like? See the `/add-template` command to register your own
Typst template instead of the stock one.

## The loop

Once an application goes out, **`/outcome`** records what happened to it — archiving the whole
apply-out folder (draft sources, both PDFs, the posting) into `archive_dir` on the day you
apply, then moving the tracker row and logging every later stage change against that archived
copy. **`/followup`** scans your Active section for rows gone quiet past `followup_after_days`
(10 by default), and for the ones you pick it drafts a nudge built only from what was actually
submitted — the archived resume's own text, the posting, and the dated log — capped at two
follow-ups per application, where the cap counts drafts rather than sends, because a draft you
read and never sent still spent the slot and a counter that waits on you to report back drifts
low and stops capping anything. Both commands write to exactly two places, your tracker and
your archive: every tracker edit prints a unified diff before it touches the file, while the
archive writes are silent appends, so the commands quote those back to you instead. When enough
applications have resolved, **`tools/calibrate.py`** joins your Closed rows to their archives
and proposes changes to `config/` — proposals only, gated behind a minimum-N floor on *both*
sides of every comparison, with every contrast that failed that floor named alongside its
actual counts, so early in a season the honest report is mostly suppressions rather than
confident advice. **Nothing in this loop sends anything and nothing edits your config:**
follow-ups are text you copy and send yourself, calibration has no `--apply` flag and will not
get one, and applying stays your hand on the button exactly as it is in `/apply`.

**Run every command from the repo root**, the same as everything else in this README — paths
inside `/apply`, `/add-template`, `/outcome`, and `/followup` are repo-relative and assume that
working directory, and so is `tools/calibrate.py`.
