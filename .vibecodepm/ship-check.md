---
name: job-radar ship-check — row 64 (decision ledger, fingerprints, four rule types)
read_by: gtm before any launch planning; the next ship-check run on this branch, which picks up from the open findings below
phase: ship-check
milestone: row 64 (judgment that is not machine-readable does not compound)
status: draft
date: 2026-09-26
reviewer: row64_reviewer (independent; did not build this)
branch: lane/row64-decision-ledger @ 216a236, PR derrtaderr/job-radar#8
---

decision: BLOCK
hard_gate: the on-site body rule (and every hyphen-bearing pattern the kill path runs) must fire on a description in the shape the live scrape actually delivers (markdown with `\-` escapes), proven by at least one fixture in that shape; until then the miss-4 mechanism the PR claims to close is dead on real data.
success_window: carried from metrics.md — activation = doctor clean + first `radar-out/<date>/queue.md`; row 64 adds "a judged posting is counted as queued, never as suppressed", which the build honours.

# Ship-check — row 64

Both `flow.md` and `metrics.md` were present and read before the walk. Both carry
`status: current — matches the build at lane/phase-4`, dated 2026-09-13, while their bodies
were edited in this branch to describe row 64; the map graded against is current in
content and stale in its own frontmatter (MAP finding, minor).

## Flows walked

- Entry point + doctor (fresh clone, own venv), before and after `cp -r config.example config`.
- The demo detour (`tools/demo.py`), reading the queue's Prior column and Flagged section.
- Happy path step 2 (`radar.py --dry-run`) and step 3 (`radar.py judge`, jid form, company/title
  form, bad verdict, unknown jid, legacy jid).
- Recovery: malformed ledger through the doctor (check 10) and through a run (WARN by row).

Stranger walk performed by `vibecodepm:user-advocate` from a fresh clone into a scratch
directory (27 shell steps, ~5 min plus reading; every documented exit code matched). Axis
verdicts for the CLI+docs+demo surface: invocation WEAK (`radar.py --help` never lists
`judge`), comprehension MIXED (ledger comments excellent; SETUP's doctor sample shows nine
lines under "Ten checks"; second-judgment semantics undocumented), persistence WEAK on the
new feature (tier-1 last-wins vs tier-2 first-wins; the fictional demo-3 verdict is copied
into the stranger's real `config/` and the doctor reports it green), recovery GOOD (every
provoked error named the file, row, or fix), waste one loop (judging into `demo-out/config`
and re-running the demo wipes the rows). Its findings are folded into the table below.

## Instrumentation

Every row in metrics.md's tables resolves to a named test that exists and passes on the
branch (749 passed, exit 0). The new counting rule ("N already judged", additive, zero
silent) is proven by `tests/test_report_row64.py` and `tests/test_row64_replay.py` and
reproduced by hand (section O of the hostile run).

## Package audit

Installable (a clone). `git ls-files` contains the tool, docs, tests, `config.example`, and
`.githooks`. No absolute local paths, no emails, no phone numbers in the shipped tree; every
company name in the new tests is invented (Northwind Analytics, Cobalt Grid, Kestrel
Dynamics, Larkspur Grid, Talent Reach Staffing, Meridian Analytics). `tools/privacy_guard.py`
exit 0. `config/` (which now holds `decisions.csv`) is gitignored by the directory line.

## Security surface

No network egress added. No secrets. The ledger is untrusted input to the run: a malformed
row degrades to a WARN naming the row, never to a crash or a silent drop of other rows
(verified: bad verdict row, header-less file, two-header file from a write race). Fail
direction on the ledger is open in the safe sense: nothing is hidden because the ledger
attaches rather than filters.

## Findings

See the reviewer's report for the full table with reproduction commands. Blocking:

- **R64-01 (blocker)** `engine/radar/rules_engine.py` on-site rule: `kill_flags` returns `[]`
  for `"This is a fully on\-site position"` (live scrape shape) and `[('onsite-body', ...)]`
  once `\-` is unescaped. No fixture in the repo carries a markdown escape; nothing in
  `scrape.py` or `pipeline.py` unescapes. The documented miss-4 fix does not fire on real data.

Important (ship after the block clears, or decide explicitly):

- R64-02 tier-3 `fp_comp` collision carries a prior verdict onto an unrelated company
  (band + common benefits set is not identity).
- R64-03 the aggregator repost that motivated the fingerprint design is not flagged
  (benefits paraphrased); its sibling req at the same company is flagged instead.
- R64-04 commute allowlists written as full state names stop matching after normalisation
  (`Colorado` vs "Denver, Colorado" now kills; matched before).
- R64-05 hybrid default rejects genuinely remote sentences ("25 days of PTO", "optional desk
  in our office", "occasional on-site offsites") → location kill where the untightened
  override passed.
- R64-06 on-site default kills "remote, hybrid, or on-site positions" under a remote header.
- R64-07 seniority band reads non-experience years ("401(k) vests after 1 year", "past 2
  years", "at least 3 years focused on HubSpot") as a junior floor: -15 on realistic bodies.

Minor: tier-1 returns the latest decision, tier-2 the earliest; `judge <unknown> --company X`
without `--title` writes a tier-1-only row the DESIGN.md says is refused; legacy-jid message
says "no record" when a record exists; two-`judge` header race on a fresh file; `radar.py
--help` does not list `judge`; flow/metrics frontmatter stale; "Bank of CO" → "bank of" in
`normalise_name`.

## Numbers reproduced

pytest 749 passed exit 0 · privacy_guard exit 0 · doctor `--config config.example` exit 0
(9 OK, 1 SKIP) · demo exit 0 (7 queued, 5 killed, 1 already judged) · dry-run exit 0 ·
`grep -rniE "openai|anthropic|claude|gpt|llm|litellm" engine/` no matches (exit 1).
