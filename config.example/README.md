# config.example

This is a complete, working configuration for a fictional persona (a data engineer
targeting remote-US senior data/platform roles). No real employer, person, or search
criteria appears in it. Its job is to make this repo runnable and legible to a stranger
on first clone, and to document the shape config files take without leaking anyone's
actual preferences.

## Use it

**The guided way: run `/setup` in a Claude Code session at the repo root.** It checks the
environment first, copies this folder for you, and then interviews you file by file — your
career facts into `profile.md`, your target titles into `queries.yaml`, the roles you never
want to see again into `rules.yaml` as named kill rules. Every pattern it writes gets read
back to you in plain English before it lands. The rest of this file is the same work done by
hand, and it is the reference `/setup` follows.

By hand:

1. **If you are reading this inside `config.example/`:** copy the whole folder to `config/`
   at the repo root — `cp -r config.example config`, **only if `config/` doesn't exist
   yet**. Run it over a populated one and `cp -r` doesn't overwrite your judgment, it NESTS:
   you end up with a second copy at `config/config.example/` that nothing reads. Your real
   files survive untouched, but so does the mistake; delete `config/config.example` to
   clean up.
   **If you are reading this inside `config/`:** this copy already happened — this folder is
   your live judgment layer. Skip straight to editing the files below.
2. Edit every file in `config/` to reflect your own search: your target titles and
   locations, your kill rules, your comp floor, your scoring weights, your output paths,
   your excluded companies.
3. `config/` is gitignored from the first commit onward. Nothing you put there — target
   roles, salary floor, excluded employers, notes on postings — ever leaves your
   machine. The engine reads `config/` at runtime but never writes your judgment back
   into a tracked file.

## What each file is

- `queries.yaml` — what to search for, which sites, which location, how fresh a
  posting has to be to matter.
- `rules.yaml` — the comp floor, the optional commute-location allowlist for
  non-remote postings, and the kill rules. Every kill rule quotes the line of the
  posting that matched it, so a kill is always overrulable, never silent.
- `weights.yaml` — the scoring model: title tiers, comp scoring, freshness scoring,
  remote and seniority bonuses.
- `settings.yaml` — output directory, state file (seen-job memory), an optional
  markdown tracker path and its active sections, and the window after which a closed
  application stops being tracked.
- `exclusions.txt` — companies never to surface again, one per line, case-insensitive
  substring match.
- `profile.md` — your career facts, and the one file the drafting side reads.

## profile.md is the claim ledger

`profile.md` is different in kind from the other files here. The rest tell the engine what
to look for; this one tells `/apply` what you are allowed to say about yourself. It holds
your contact frontmatter, a summary, every role with its factual bullets, skills,
education, and an evidence-notes section carrying the context behind each number. The
drafter may only write a resume or cover-letter claim that traces back to a line in it.
Anything a posting invites that your ledger doesn't support comes back as
`[CONFIRM: <claim>]` for you to answer, rather than getting quietly written into a PDF
with your name on it. So fill it in generously and truthfully — longer than any single
resume needs, since tailoring works by selecting from a deep ledger, not by embellishing a
thin one. Like everything in `config/`, it never leaves your machine.
