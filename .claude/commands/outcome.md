---
description: Record what happened to one application — archive it on apply, log a stage change, or close it out — by editing the tracker and the archive through the checked tools. Never sends anything.
argument-hint: <company> and what happened (e.g. "Cobalt Grid — applied", "Cobalt Grid — screen scheduled Tuesday", "Cobalt Grid — rejected after the final round")
---

# /outcome

Move one application's record forward: archive it the day it goes out, log a stage change
while the detail is still fresh, or close it with a lesson worth carrying into the next one.

`$ARGUMENTS` names a company and says what happened, in the human's own words. "Cobalt Grid
— applied." "Cobalt Grid — they scheduled the HM round for Tuesday." "Cobalt Grid —
rejected, final round, they went with an internal candidate."

Everything this command writes lands in two places and only two: the tracker markdown file,
and the archived application's `outcome.md`. Both are the human's own record of their own
search, which is why every edit here is printed as a diff before it is written, and why none
of it is inferred from a date, a heuristic, or an assumption about what probably happened
next.

**Every command in this file runs from the repo root, using `.venv/bin/python`.** Paths are
repo-relative throughout.

---

## Step 1 — Read the config, then check the tracker before touching it

The tracker path, the archive directory, and the follow-up window all live in the config,
and none of them should be typed from memory:

```bash
.venv/bin/python -c "
from pathlib import Path
from engine.radar.config import load_config
cfg = load_config(Path('config'))
print('tracker:', cfg.tracker_path)
print('archive_dir:', cfg.archive_dir)
print('followup_after_days:', cfg.followup_after_days)
"
```

`tracker: None` means `config/settings.yaml` has no `tracker:` set. Stop and say so — there
is no file to record into, and guessing at a path is how a second tracker gets created in a
directory nobody looks at. If `config/` itself doesn't exist, `cp -r config.example config`
is the fix.

Then check the tracker:

```bash
.venv/bin/python tools/tracker_cli.py check <tracker path>
```

Exit 0 prints `tracker: OK (N rows across K sections)`. Exit 1 prints one plain-English line
per violation, each naming a line number:

```
line 5: Last touch 'TBD' has no ISO date (Active section)
```

**Never edit a tracker that fails the check.** The editing tools match rows by Company+Role
and splice cells by pipe position, so a row with the wrong cell count or a shifted column is
a row where an edit lands somewhere other than where it looks like it landed. Report the
violations, fix them with the human (or let them fix them by hand), re-check, and only then
go on. A malformed tracker is a five-minute problem now and an untraceable one after three
more edits have been written on top of it.

## Step 2 — Name the transition before you make it

There are three, and which one this is decides everything downstream. Say it out loud before
running anything:

| What happened | Transition | Sections |
|---|---|---|
| The human applied | archive, then move | Drafted but not applied → Active |
| A stage moved, or anyone made contact | touch + log, row stays put | Active |
| It ended, any way at all | move | Active → Closed |

Two things to settle here rather than later.

**The row may not be where you expect.** `move` matches exactly one row by Company+Role in
the `--from` section and refuses otherwise, by design:

```
error: no row found for 'Nope Inc' / 'Engineer' in Active section
```

That is information, not a failure to work around. An application made straight off a
posting never passed through "Drafted but not applied," so there is nothing to move — use
`tracker_cli.py add --section Active` instead, with the same columns Step 3a would have set.
Never invent a `--from` section to make a `move` succeed.

**`hired`, `offer`, and `offer declined` get recorded only on the human's explicit word.**
An offer is not inferable from a final round going well, and "they said they'd be in touch
with good news" is not an offer. If the arguments are ambiguous about which of those
happened, ask. This is the one place where a wrong guess is written into a permanent record
and later read back by a calibration run as though it were fact.

## Step 3a — Applied

**Archive first, then move the tracker row.** `archive_application` copies the whole
apply-out folder — draft sources, both PDFs, `jd.md`, any subdirectory — into the archive
slug and writes `outcome.md` alongside it. Run it before the tracker edit, because the two
failure orders are not symmetric: an archive that exists while the tracker still says
"Drafted" is a record one command behind, visible and fixable, while a tracker that says
"Active" with no archive behind it points at a snapshot that was never taken. `apply-out/`
gets overwritten by the next drafting run for the same company, so the snapshot has no
second chance.

```bash
.venv/bin/python -c "
from pathlib import Path
from engine.loop.archive import archive_application
dest = archive_application(
    Path('apply-out/<company>-<slug>'),
    Path('<archive_dir from Step 1>'),
    {'company': '<Company>', 'role': '<Role>', 'applied': '<YYYY-MM-DD>'})
print(dest)
"
```

All three meta keys are required; a missing one raises `ArchiveError` naming the key, before
anything is written. The archive slug is the apply-out folder's own name, so the two trees
line up by inspection. The written `outcome.md` is small on purpose:

```
---
company: Cobalt Grid
role: Data Platform Engineer
applied: 2026-09-13
followups: 0
---

## Log
- 2026-09-13: applied
```

**A slug that already exists is refused, not overwritten:**

```
ArchiveError: archive slug 'cobalt-grid-data-platform-engineer' already exists at ...
```

Which almost always means this application was already archived — check the existing
`outcome.md` before doing anything else. If it is genuinely a second application to the same
company and role months apart, the fix is a distinct apply-out folder name, never deleting
the first archive.

Then move the row. Active carries columns Drafted doesn't, so they come in through `--set`:

```bash
.venv/bin/python tools/tracker_cli.py move <tracker path> \
  --company '<Company>' --role '<Role>' \
  --from 'Drafted but not applied' --to 'Active' \
  --set 'Stage=Applied' \
  --set 'Last touch=<YYYY-MM-DD, the date they applied>' \
  --set 'Next step=Wait for response' \
  --dry-run
```

`Stage` and `Last touch` are the two Active requires and Drafted has no answer for.
`Next step` is the third, and it is the easy one to miss: it exists in BOTH tables, so
without a `--set` it carries the drafting-stage value across verbatim and the new Active row
reads `Finish cover letter` on an application that already went out. Any column that exists
only in Drafted (`Resume`) is dropped; it lived its life there.

Columns vary between trackers, since the check only requires Company, Role, and Last touch in
Active. Read the human's actual header row and set what it has. An unknown column name is
refused, naming it:

```
error: unknown column(s) for Active section: Stag
```

## Step 3b — A stage moved, or anyone made contact

The row stays in Active. Two writes, and they are not redundant — the tracker cell is what
the staleness scan reads, and the archive log is what a calibration run and a follow-up draft
read months later.

```bash
.venv/bin/python tools/tracker_cli.py touch <tracker path> \
  --section 'Active' --company '<Company>' --role '<Role>' \
  --column 'Last touch' --value '<YYYY-MM-DD>'
```

```bash
.venv/bin/python -c "
from pathlib import Path
from engine.loop.archive import append_log
append_log(Path('<archive_dir>/<slug>'), '<YYYY-MM-DD>',
           'HM round scheduled for Tuesday')
"
```

`touch` rewrites exactly one cell and leaves every other cell in the line byte-for-byte
intact, annotations and spacing included. `append_log` adds one dated line and disturbs
nothing above it. Log what was said, in the human's words, short: `screen scheduled`,
`recruiter asked for references`, `take-home sent, due Friday`. A log line is evidence for a
follow-up draft later, so a vague one is worth less than none.

Also `touch` the `Stage` and `Next step` columns when they changed. A tracker whose Stage
still says `Applied` through an HM round is one the human stops trusting, and it is the same
one command.

### Offer a thank-you note, in the same turn

When the stage advanced because of a conversation — a screen, an HM round, a panel — offer
to draft a thank-you note right here, without being asked. It is worth most within the day
and it is the thing that gets skipped when the tracker edit already feels like the chore
completed.

**A draft only.** Same rule as everywhere else in this repo: it goes in a message for the
human to read, edit, and send from their own mail client. This command does not send it and
does not offer to. If they want it, write three or four sentences that name something
specific from the conversation — nothing generically enthusiastic, and nothing claiming
anything about their experience that isn't already in `config/profile.md`.

## Step 3c — It ended

Every ending goes to Closed: rejection, offer, offer declined, withdrawal, a role frozen, a
timeout, silence that has gone on long enough that the human calls it. Closed is where the
calibration run reads from, so an application that quietly stays in Active forever is one
that teaches nothing.

```bash
.venv/bin/python tools/tracker_cli.py move <tracker path> \
  --company '<Company>' --role '<Role>' \
  --from 'Active' --to 'Closed' \
  --set 'Date closed=<YYYY-MM-DD>' \
  --set 'Outcome=<Rejected | Rejected at screen | Offer | Offer declined | Withdrew | Timed out | No response>' \
  --set 'Reason=<one clause, from what the human said>' \
  --set 'Carry-forward lesson=<the human supplies this — see below>' \
  --dry-run
```

**Outcome wording is read back by `calibrate.py`, so it is worth getting close to those
words.** It classifies by case-insensitive substring, first match wins: `offer` (so "Offer
declined" counts as an offer, because they made one), `screen` before the generic `rejected`
(a screening-out is the opposite signal from a late-stage rejection), `timed out`,
`no response` / `silence` / `ghost`, `withdrew` / `withdrawn`, then `rejected`. Anything else
lands in an `other` bucket carrying the exact text the human typed — visible in the report,
never silently dropped, and never guessed at. Don't distort what happened to hit a keyword;
do use the plain word for it when the plain word is accurate.

**The human supplies the carry-forward lesson. Ask for it; do not write one.** Everything
else in that row is a fact being transcribed. The lesson is a judgment about their own search
— "ask about internal candidates at the screen," "confirm the comp band before the HM round"
— and a plausible-sounding sentence generated from the outcome is exactly the kind of thing
that reads as wisdom and carries none. If they don't have one, `--set 'Carry-forward
lesson='` and leave it empty. An empty cell is honest; an invented one is noise that outlives
the application.

Then log the close in the archive too, so the outcome sits with the materials that produced
it:

```bash
.venv/bin/python -c "
from pathlib import Path
from engine.loop.archive import append_log
append_log(Path('<archive_dir>/<slug>'), '<YYYY-MM-DD>',
           'closed — rejected after the final round')
"
```

## Step 4 — After a close, suggest a calibration run

**Every move into Closed ends by suggesting a calibrate run.** One line, at the end of the
presentation:

> Closed count changed. `.venv/bin/python tools/calibrate.py <tracker path> --config config`
> reads the whole season and proposes config changes. Worth a look whenever you're curious.

Every time, not "every fifth close." The alternative was a `last_calibrated` marker in the
tracker's own Schema notes, and it was rejected: it is hidden state in a file the human edits
by hand, it goes wrong silently, and it makes the suggestion depend on bookkeeping rather
than on something true. Suggesting every time is the honest version — the report is read-only
and takes a second to produce, and the human is free to ignore the line entirely. They will,
most times, and that costs nothing.

What the run does, so the suggestion means something: it joins Closed rows to their archived
applications, buckets the outcomes, and compares what the interviewed applications had in
common against what the negative ones did. It requires N on BOTH sides of a contrast before
it will propose anything, and it names every contrast that failed that floor with its actual
Ns rather than showing only the ones that passed. It has no write path to `config/` at all.
Early in a season the honest report is mostly suppressions, which is the correct output and
not a broken run.

## Step 5 — Present, and stop

Hand back:

1. **The diff** the tool printed, for every edit made. That is the receipt. If anything ran
   with `--dry-run`, say clearly that nothing was written yet and ask for the yes.
2. **What was recorded, in one line** — the transition, the row, the archive path if one was
   written.
3. **Anything that needs the human**: a tracker violation from Step 1, a missing
   carry-forward lesson, an ambiguity about whether an offer actually happened, an
   `ArchiveError` on a slug that already exists.
4. **The thank-you draft** (Step 3b) or **the calibrate suggestion** (Step 4), when either
   applies.

Then stop. Nothing here sends an email, replies to a recruiter, or contacts anyone. It
records what the human did, in the human's own file, and the next move is theirs.
