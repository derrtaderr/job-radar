---
description: Look up the hiring manager and recent hires at the top postings' companies through Clay, and record what was found.
argument-hint: [N, default 10]
---

# /paths

Find a person at each company worth applying to, so `/apply` can put the steps in the right
order and `/reach` has someone to write to.

**Every command in this file runs from the repo root, using `.venv/bin/python`.**

## Step 1 — Choose the companies

The top N survivors in today's `radar-out/<date>/queue.md` (N from `$ARGUMENTS`, default 10),
plus every company in the tracker's drafted section:

```bash
.venv/bin/python tools/network_cli.py paths --tracker
```

Decide on the **Lookup** column, not the Path column: look up every company whose Lookup
is `never` or `stale`, including companies that already show a warm path. A warm ask that times
out falls back to the hiring-manager note, so the hiring manager has to be known either way.
Say how many lookups that leaves before spending any Clay credits.

## Step 2 — Look each one up in Clay

For each company, use the Clay connection's contact search for (a) the likely hiring manager
for the posting's function and (b) people in that function whose current role started within
about 180 days. Record what was found:

```bash
.venv/bin/python tools/network_cli.py add --company "<Company>" --result found \
  --person "<Name>|<Title>|<LinkedIn URL>|hiring_manager" \
  --person "<Name>|<Title>|<LinkedIn URL>|recent_hire|<YYYY-MM-DD started>"
```

If the search ran and found nobody, record `--result none`. A failed lookup writes nothing.
An error or a timeout is not a `none`, and recording it as one would tell the human nobody is
there when nobody looked.

## Step 3 — Report

Re-run `network_cli.py paths` for the companies looked up and print the table, plus the Clay
credits used. The next radar run's queue carries the Path column.
