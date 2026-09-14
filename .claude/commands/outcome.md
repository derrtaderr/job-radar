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
search, so nothing here is inferred from a date, a heuristic, or an assumption about what
probably happened next.

**The two write paths report differently, and it is worth knowing which you are looking at.**
Every `tracker_cli.py` edit prints a unified diff of the change before writing, so the tracker
edits carry their own receipt. The archive writes — `archive_application` and `append_log` —
print no diff; they are silent appends to a file nobody else is editing. So quote the log line
you wrote in the presentation, because nothing else will show it.

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
| A stage moved, or anyone made contact | log + touch, row stays put | Active |
| It ended, any way at all | move | Active → Closed |

Three things to settle here rather than later.

### Resolve the archive slug by listing, never by construction

Several steps below need `<archive_dir>/<slug>`. **List the archive and match against what is
actually there.** Do not build the path out of the company name, and do not assume it matches
the apply-out folder you have in mind:

```bash
ls <archive_dir>
```

```bash
.venv/bin/python -c "
from pathlib import Path
from engine.loop.archive import read_outcome, ArchiveError
for slug in sorted(p for p in Path('<archive_dir>').iterdir() if p.is_dir()):
    try:
        o = read_outcome(slug)
        print(f'{slug.name}  |  {o[\"company\"]}  |  {o[\"role\"]}  |  applied {o[\"applied\"]}  |  followups {o[\"followups\"]}')
    except (ArchiveError, OSError) as e:
        print(f'{slug.name}  |  UNREADABLE: {e}')
"
```

Match on the `company` and `role` in the frontmatter, which are the values a human typed, not
on the slug's spelling. A constructed path is how you end up writing a log line into a
directory that does not exist, or silently creating one. If nothing matches, the application
was never archived — that is Step 3d, not a naming problem to solve by trying variants.

### The row may not be where you expect

`move` matches exactly one row by Company+Role in the `--from` section and refuses otherwise,
by design:

```
error: no row found for 'Nope Inc' / 'Engineer' in Active section
```

That is information, not a failure to work around. An application made straight off a posting
never passed through "Drafted but not applied," so there is nothing to move. **Add the row
instead.** `add` builds the row from the `--set` values alone — it has no source row to
inherit Company and Role from, and it will happily write a row with both cells empty, which
`check` passes (it only requires the COLUMNS to exist) and which `move` and `touch` can then
never match again. So set them explicitly, first:

```bash
.venv/bin/python tools/tracker_cli.py add <tracker path> \
  --section 'Active' \
  --set 'Company=<Company>' \
  --set 'Role=<Role>' \
  --set 'Stage=Applied' \
  --set 'Last touch=<YYYY-MM-DD>' \
  --set 'Next step=Wait for response' \
  --dry-run
```

Read the diff before writing, and confirm Company and Role are both populated in the new line.
Any column the human's Active table has and this list doesn't gets an empty cell, which is
fine for `Source` or `Notes` and is not fine for those two. Never invent a `--from` section to
make a `move` succeed.

### Offers and hires are recorded only on the human's explicit word

**`hired`, `offer`, and `offer declined` get recorded only on the human's explicit word.** An
offer is not inferable from a final round going well, and "they said they'd be in touch with
good news" is not an offer. If the arguments are ambiguous about which of those happened, ask.
This is the one place where a wrong guess is written into a permanent record and later read
back by a calibration run as though it were fact.

**For a hire, write `Outcome=Offer accepted`** and put the detail in `Reason`. It reads
plainly, and it classifies as an offer, because `calibrate.py` matches `offer` first. Avoid
`Hired` on its own: it matches nothing in the mapping table and lands in the `other` bucket.
That is not a bug and nothing is lost — `other` prints the exact text in the report and is
excluded from every contrast, which is the right treatment for a word nobody has interpreted.
It just means the one outcome the whole search was for sits outside the analysis. If the human
prefers `Hired`, use their word and say this out loud rather than overriding them.

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

**This means the application was genuinely already archived.** It is not a leftover from a
half-finished attempt — `archive_application` stages the whole copy in a temporary directory
and renames it into place only after the last file lands, so a failed archive leaves nothing
behind and the retry path is always clear. Read the existing `outcome.md` (its Log will say
when it was applied) and carry on from there; the tracker move below may still be outstanding.
If it is genuinely a second application to the same company and role months apart, give the
new one a distinct apply-out folder name. Never delete the existing archive to make room.

**If the apply-out folder is gone, the archive cannot be created faithfully:**

```
ArchiveError: nothing to archive: apply-out/cobalt-grid-data-platform-engineer does not exist ...
```

Do not rebuild it. Re-drafting from the current `config/profile.md` produces a resume that
was never sent, filed as though it were, and a follow-up drafted off it months later would
quote claims the employer never received. Take the no-archive path in **Step 3d** instead:
record the tracker side, say plainly that no archive exists, and move on.

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

### Committing a `--dry-run`

`--dry-run` prints the diff and writes nothing. **Show the human that diff, and on their yes,
re-run the identical command with `--dry-run` removed and nothing else changed.** Not a
rebuilt command, not a tidied one — the diff they approved is only a promise about the exact
argument list that produced it. Then show the second diff too; it is the receipt that the
write happened, and it should match what they just approved.

Which edits get gated this way, and why it is not all of them:

- **`move` is always gated.** It rewrites a whole row across two tables, drops source-only
  columns, and carries values you composed (`Next step`, a `Reason` clause). The blast radius
  is a row, and the diff is the only place a wrong `--set` is visible before it lands.
- **`add` is always gated**, for the reason in Step 2: it can write a row with empty
  Company/Role that nothing can match again.
- **`touch` is not gated by default.** One cell, one value, and in almost every case the value
  came verbatim from the human ("they replied today"). Gating it turns a one-line update into
  a two-step ceremony, and a gate that re-asks an answered question trains people to skim
  past the ones that matter. The tool prints the diff on the real run regardless, so the
  receipt is there either way. Gate a `touch` when the value is one you inferred rather than
  one they said — a date reconstructed from "last week," or a `Stage` you named for them.

## Step 3b — A stage moved, or anyone made contact

The row stays in Active. Two writes, and they are not redundant — the tracker cell is what
the staleness scan reads, and the archive log is what a calibration run and a follow-up draft
read months later.

**Log first, then touch the tracker**, which is the same argument as Step 3a's archive-first
rule applied one step down. A log line with a `Last touch` that hasn't moved yet leaves the
row looking a day staler than it is, so the next scan surfaces it and the gap is one command
away from closing. A moved `Last touch` with no log line behind it is the opposite: the row
drops out of every scan, looking exactly like a row that is fine, while the thing that was
actually said is gone.

```bash
.venv/bin/python -c "
from pathlib import Path
from engine.loop.archive import append_log
append_log(Path('<archive_dir>/<slug>'), '<YYYY-MM-DD>',
           'HM round scheduled for Tuesday')
"
```

```bash
.venv/bin/python tools/tracker_cli.py touch <tracker path> \
  --section 'Active' --company '<Company>' --role '<Role>' \
  --column 'Last touch' --value '<YYYY-MM-DD>'
```

`append_log` adds one dated line and disturbs nothing above it, silently — it prints no diff,
so quote the line you wrote when you present. `touch` rewrites exactly one cell and leaves
every other cell in the line byte-for-byte intact, annotations and spacing included, and it
does print a diff. Log what was said, in the human's words, short: `screen scheduled`,
`recruiter asked for references`, `take-home sent, due Friday`. A log line is evidence for a
follow-up draft later, so a vague one is worth less than none.

Also `touch` the `Stage` and `Next step` columns when they changed. A tracker whose Stage
still says `Applied` through an HM round is one the human stops trusting, and it is the same
one command.

If the slug lookup from Step 2 found no archive, skip the `append_log` and still do the
`touch` — that is Step 3d.

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

Log the close in the archive first, same ordering and same reason as Step 3b, so the outcome
sits with the materials that produced it:

```bash
.venv/bin/python -c "
from pathlib import Path
from engine.loop.archive import append_log
append_log(Path('<archive_dir>/<slug>'), '<YYYY-MM-DD>',
           'closed — rejected after the final round')
"
```

Then run the `move` above with `--dry-run`, show the diff, and **on the human's yes re-run the
identical command without `--dry-run`.** A close is the most gated edit in this command: it
carries a `Reason` clause you composed and a lesson in their words, and it is the row a
calibration run reads back as fact months later.

## Step 3d — When there is no archive

The slug lookup in Step 2 found nothing. The realistic cause is an application that predates
this part of the tool — applied by hand, or applied before `/outcome` existed — and it will be
common for a while. It is not an error and it does not block anything.

**Do the tracker edit exactly as written.** Every transition above works without an archive;
the tracker is the load-bearing record and it stays complete.

**Skip the `append_log` and say so in the presentation.** One line, naming what was skipped:

> No archive for this one, so the log line was skipped. The tracker row is updated.

Say it every time rather than only the first, because a silently-skipped write is
indistinguishable from one that happened.

**Never back-fill an archive from an apply-out folder.** Not from a folder still sitting there
with a matching name, and not by re-drafting. An `apply-out/` folder is overwritten by the next
drafting run for that company, so a folder that looks right may hold a later draft, or a
different role's, and neither is what was submitted. An archive's whole value is that it holds
the documents the employer actually received — a follow-up drafted from it quotes them, and a
calibration run reads its `jd.md` as the posting that was applied to. A plausible
reconstruction filed as a record is worse than no record, because nothing downstream can tell
the difference.

What that costs is worth naming plainly: this application will not appear in `calibrate.py`'s
joined set, and it is counted in the report's unjoined rows. That is the honest outcome, and
the report is built to say so out loud rather than quietly shrinking its own denominator.
`/followup` will decline to draft for it for the same reason.

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

1. **The diff** `tracker_cli.py` printed, for every tracker edit made. That is the receipt for
   that half. If anything ran with `--dry-run`, say clearly that nothing was written yet and
   ask for the yes.
2. **The archive writes, quoted**, because they print no diff and nothing else will show them:
   the archive path `archive_application` returned, and the exact log line `append_log` added.
   An unquoted silent append is a write the human has no way to check.
3. **What was recorded, in one line** — the transition and the row.
4. **Anything that needs the human**: a tracker violation from Step 1, a missing
   carry-forward lesson, an ambiguity about whether an offer actually happened, an
   `ArchiveError` on a slug that already exists, or an outcome.md that would not parse.
5. **A skipped log line** (Step 3d), whenever there was no archive to write to.
6. **The thank-you draft** (Step 3b) or **the calibrate suggestion** (Step 4), when either
   applies.

Then stop. Nothing here sends an email, replies to a recruiter, or contacts anyone. It
records what the human did, in the human's own file, and the next move is theirs.
