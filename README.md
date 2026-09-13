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
  closed. Requires `tracker:` set in `config/settings.yaml`.
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
