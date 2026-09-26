# WIRING.md — the vault-side edits row 64 needs

This lane never touches the vault. Everything the vault side needs is below as exact
old→new strings, for the orchestrator to apply.

Three edits, plus one optional config addition. Nothing here is required for the repo's own
tests, the doctor, or the demo to pass — those are green without it. What it buys is the
loop closing: `radar.py judge` only compounds if the daily routine actually calls it, and a
`read_by:` that never fires is the failure mode this vault already has a rule about.

**Nothing to migrate.** `config/state.json` keeps working untouched. Its value grew from a
date string to a dict, and the reader accepts both — the first run after this change writes
new entries in the new shape and leaves every old entry exactly as it was.

---

## Edit 1 — `/daily` Step 2.8, item 3: record every verdict

**File:** `.claude/commands/daily.md`

The judgment pass is where the decision is made, so it is where the decision has to be
written down. Without this the verdict lives in one session's context and the same req comes
back as a fresh top-scored row days later.

**OLD** (the last two sentences of item 3):

```
location kill that still stands means the JD said nothing remote-positive — worth a
   skim only when the company matters. A wrongly-flagged role gets drafted like any pick.
```

**NEW:**

```
location kill that still stands means the JD said nothing remote-positive — worth a
   skim only when the company matters. A wrongly-flagged role gets drafted like any pick.

   **Record every verdict, in this session, as the pass is made** (added 2026-09-26, row
   64): for each posting read and ruled OUT, run
   `~/Projects/job-radar/.venv/bin/python ~/Projects/job-radar/radar.py judge <jid>
   --verdict kill --reason <slug> --config ~/Projects/job-radar/config`. The `<jid>` is the
   id in the queue row's `jd` link. The `<slug>` is short and for Jason's own recognition
   later (`bi-analytics`, `too-junior`, `wrong-stack`). This writes
   `~/Projects/job-radar/config/decisions.csv`, which every later run reads: a judged
   posting comes back into the queue with that verdict in its **Prior** column rather than
   as a fresh row. It is never hidden and never scored down — the point is that Jason sees
   what he already decided, not that the engine decides for him.

   A kill recorded only as a line of reasoning in the brief is a kill the next run cannot
   see. That is the miss this closes: three re-surfaces of hand-killed reqs in four days,
   the last of them at the top of the queue.
```

---

## Edit 2 — `/daily` Step 2.8, item 5: a drafted pick is a verdict too

**File:** `.claude/commands/daily.md`

**OLD:**

```
5. **File each drafted pick** as a row in `applications-tracker.md` → "Drafted but not
   applied", with source "job-radar" and the posting URL. The tracker is what suppresses
   re-surfacing; an unfiled draft WILL come back tomorrow.
```

**NEW:**

```
5. **File each drafted pick** as a row in `applications-tracker.md` → "Drafted but not
   applied", with source "job-radar" and the posting URL. The tracker is what suppresses
   re-surfacing; an unfiled draft WILL come back tomorrow.

   **The same pick gets a ledger row** (added 2026-09-26, row 64):
   `radar.py judge <jid> --verdict draft --reason <slug>` alongside the tracker row. The
   tracker suppresses by COMPANY, which is the right unit for "we are already talking"; the
   ledger records by POSTING, which is the right unit for "I read this req and decided."
   Both, not either: the tracker stops the company re-surfacing while a conversation is
   live, and the ledger is what still tells Jason "you drafted for this one" after the
   tracker row has closed and the company is free to surface again.
```

---

## Edit 3 — the private config mirror's README

**File:** `projects/job-search/radar-config/README.md`

The mirror documents Jason's real judgment layer. Two files in
`~/Projects/job-radar/config/` are new or changed, and both are written by the tool rather
than by hand, so the README is the only place they get explained.

**NEW** (append a section; no old text is replaced):

```
## Files the tool writes (added 2026-09-26, row 64)

- `decisions.csv` — the decision ledger. Written by `radar.py judge`, read by every run.
  Columns: `jid, company, title, verdict, reason, date, url`. `verdict` is exactly `kill` or
  `draft`. `#` comment lines are ignored. A judged posting returns to the queue with its
  verdict in the **Prior** column, at the score it would otherwise have — it is never
  suppressed and never ranked down. Matching tries the exact `jid`, then the normalised
  `(company, title)` pair, then the posting's content fingerprint, which is how a req
  reissued under a new LinkedIn id still finds its row.
- `state.json` — seen-job memory, now also carrying the company, title and two content
  fingerprints each run recorded. The old `jid -> "YYYY-MM-DD"` shape still loads, so there
  is nothing to migrate; entries written before 2026-09-26 stay exactly as they are.

Both hold real employer names and real decisions. They live in the gitignored `config/` and
stay there.
```

---

## Optional — turn the seniority floor on in Jason's real config

**File:** `~/Projects/job-radar/config/rules.yaml` (NOT in the vault; Jason's call, and it
needs no vault edit at all)

The three other new rules apply automatically — `onsite_phrases` and `hybrid_phrases` fall
back to the engine default when the key is absent, so an existing config gets those fixes
with no action. **`seniority` does not**, deliberately: a floor is a personal preference
like `comp_floor`, and there is no honest default to invent for someone who never stated
one. Until this block exists, the "1-4 years, early in their career" class still ranks on
title and comp alone.

**NEW** (append to `rules.yaml`):

```yaml
seniority:
  min_years: 5        # a stated floor below this costs `penalty` points
  penalty: 15
  stretch_years: 10   # a floor at or above this is flagged, and costs nothing
```

Neither end ever kills. The failure was a junior req RANKING second, not a junior req being
visible.

---

## Observed, and deliberately NOT changed by this lane

`/daily` Step 2.8 item 7 still points `--check` at
`builds/job-radar/.venv/bin/python builds/job-radar/radar.py --check`, while item 1 says the
public track at `~/Projects/job-radar` replaced `builds/job-radar` on 2026-09-13. Item 7 also
cites `builds/job-radar/SPEC.md`. That looks like a stale path from the migration, and it
means the `--check` step is running the retired engine against a config that may no longer
be there. It is outside this row's scope and is reported rather than fixed — a path change in
a vault command is a decision, not a detail.
