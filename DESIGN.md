# job-radar: design and boundaries

## What this is

job-radar is a deterministic job-search radar and the application workbench built on top of
it. It scrapes fresh postings from public job boards, runs them through a set of standing
kill rules, scores whatever survives, and hands back a ranked queue meant to be read inside
a Claude Code session. From that queue it drafts and verifies an application, records what
happened to it, and eventually reads a season of outcomes back against the rules that
produced them.

Nothing about matching or ranking is generative. A posting either trips a rule or it
doesn't, and every rejection quotes the exact line of the posting that triggered it, so a
human can check the engine's homework in seconds instead of trusting a black box.

## Three subsystems

The repo is one tool with three stages, and they are deliberately separable — each is
useful without the next one existing, and each fails on its own terms.

**Radar** (`radar.py`, `engine/radar/`) is sourcing and triage: scrape, suppress what's
already in play, filter titles, apply kill rules, score, write a day folder holding the
ranked queue and the full text of every posting the run judged. It is a pure pipeline with
a thin CLI around it; the CLI is the only layer that touches the clock, the network, or the
filesystem, which is why a whole run's behavior is testable without a single real request.

**Drafting** (`engine/draft/`, `/apply`, `/add-template`) turns one ranked posting into an
application: a Typst resume and cover letter drafted under
a claim gate, compiled, verified against a page limit and a set of contact literals
(`tools/verify_pdf.py`), and keyword-checked against the posting (`tools/ats_check.py`).
Templates resolve through a registry so a person's own layout is a registration rather than
a fork.

**Loop** (`engine/loop/`, `tools/tracker_cli.py`, `tools/calibrate.py`, `/outcome`,
`/followup`) records what happened. An application is archived on the day it goes out —
sources, PDFs, and the posting as it read then — and every later stage change is logged
against that archived copy. Quiet applications resurface past a threshold. Once enough have
resolved, `tools/calibrate.py` joins the closed rows to their archives and proposes
adjustments to the rules that produced them.

Calibration is what makes the three stages a loop rather than a pipeline: the judgment in
`config/` produces applications, the applications produce outcomes, and the outcomes are
read back against the judgment. Every step of that return path stops at a proposal.

## Two boundaries

### Code and judgment

The repo is split into a generic layer and a personal layer, and the split is structural,
not a convention someone has to remember.

`engine/` and `tools/` hold all of the code: scrapers, the kill-rule evaluator, the scorer,
the queue builder, the template registry, the PDF and ATS checks, the tracker parser and
editor, the calibrator. This code has no opinions about any specific person's job search.
It reads configuration and produces output; it does not encode anyone's preferences
directly.

`config/` holds the judgment layer: the kill rules, scoring weights, target roles, comp
floor, excluded companies, the tracker's location, and `profile.md` — the claim ledger the
drafting side is allowed to write from. This directory is gitignored in its entirety. It
never enters version control, and the engine cannot run meaningfully without one being
supplied at runtime, which forces every user to bring their own.

`config.example/` is checked in and ships with the repo. It is a complete, working
configuration for a fictional persona; no real employer, person, or search criteria appears
in it. Its job is to make the repo runnable and legible to a stranger on first clone, and
to document the shape config files take without leaking anyone's actual preferences.

### Deterministic tools and the session that runs them

The second boundary is about who decides what. Everything consequential lives in a
deterministic, tested tool: parsing a tracker, editing a row, compiling a document,
verifying it, archiving an application, computing a calibration contrast. The slash
commands in `.claude/commands/` are procedures an LLM session follows — reading postings,
drafting prose, asking the questions that turn a person's experience into a config file.

The rule that keeps this honest is that generative judgment never gets write access to
anything structured. A session drafts a resume; a tool verifies the PDF. A session decides
a row should move; a tool moves it and prints a unified diff first. A session reads a
season of outcomes; the tool computes the contrast, applies the floors, and refuses to
propose past its data. Prose steps are where flexibility belongs, and every place the
system could be confidently wrong is a function with tests around it.

## Thesis: deterministic rules, judgment stays with the human

The engine makes no calls to a language model, on principle, not as a temporary limitation.
Deterministic rules are reproducible: the same posting run through the same config always
produces the same kill or the same score, which means the rules can be tuned, versioned,
and debugged like any other code. An LLM-based filter would trade that reproducibility for
fuzzy judgment at exactly the point where the cost of a wrong call — silently dropping a
posting a person would have wanted — is highest and hardest to detect.

Judgment still happens, just later and by a human, on the ranked report the engine produces
inside a Claude Code session. That's the intended second stage: the engine narrows a large,
noisy stream of postings down to a small, evidenced list; a person (assisted by an LLM
session reading that list, if they choose) makes the actual calls. Every kill is
overrulable, because every kill is visible: it names the rule that fired and quotes the line
of the posting that matched it, so overriding it is a one-line decision, not an archaeology
project.

## Honesty mechanics

The thesis above is a claim about the system's design. These are the mechanisms that make
it true in the code, each closing a specific way a tool like this could quietly overstate
what it knows.

**No LLM in the engine.** Stated above as thesis; enforced here as a boundary. Narrowing
and scoring are deterministic functions of config and posting text, and every generative
step lives in its own explicit, human-triggered stage.

**Kills are quoted and overrulable.** A kill carries the rule's name and the matched line
from the posting. The report prints both, and the full posting text is written into the
same day folder as the queue — for kills as well as survivors — so a suspected false kill
is checkable off disk rather than on faith. A rule's configured `reason` is deliberately
not rendered in the queue; it lives next to the pattern, which is where a rule gets traced.

**The claim gate, and `[CONFIRM]`.** Every drafted resume or cover-letter claim must trace
to a line in the user's own `profile.md`. Rephrasing and re-emphasizing real experience for
a posting's vocabulary is the work; inventing a skill, a metric, or a responsibility is
not. A claim the posting invites but the profile doesn't support is written into the draft
as a visible `[CONFIRM: ...]` marker — and reaches the compiled PDF that way on purpose, so
an unsupported claim is something a person answers rather than something that quietly
ships.

**Gaps stay visible.** The ATS check reports missing JD vocabulary as information, never as
something to fix by padding. The report says so in its own closing line: gaps are gaps, and
a keyword the profile doesn't earn stays a gap.

**The follow-up cap counts drafts, not sends.** Two per application, incremented when a
follow-up is drafted rather than when one is sent. Nothing in this system sends anything,
so a cap that counted sends would never fire; and a draft a person read and decided not to
send still spent the slot.

**Calibration floors, named suppressions, and ambiguous joins.** A proposal requires a
minimum N on *both* sides of a contrast plus a real gap between the rates. Contrasts that
fail the floor are not dropped — they are printed with their actual counts, so a report
built on four applications cannot read like one built on forty. Closed rows are joined to
their archives in two passes (every exact match first, across all rows, before any
substring matching runs anywhere), and a row that more than one archive could match joins
nothing and is reported by name with the candidates it could not choose between. Silently
pairing rows to archives by slug order would produce a clean-looking 100% join rate with
every downstream contrast scored against the wrong postings, and there would be no symptom.

**Nothing is sent, and nothing is auto-applied.** Follow-ups are text a person copies and
sends. Calibration has no `--apply` flag and will not get one; it proposes and stops.
Applying is always a human action. The loop writes to exactly two places, the tracker and
the archive, and every tracker mutation prints a unified diff before touching the file and
supports `--dry-run`.

## Privacy model

Nothing about a real person's job search belongs in this repository's version-controlled
history. Personal data — target roles, salary floors, excluded employers, notes on specific
postings, resumes, application state — lives exclusively in gitignored directories:
`config/` for judgment and state, `radar-out/` for run output, `apply-out/` for drafts,
`archive/` for what actually went out, `templates/custom/` for layouts that may embed a
contact header. The engine reads from those locations at runtime but never writes example
data into them, and no code path serializes personal config back into a tracked file.

A privacy guard scans tracked files for email addresses, phone numbers, and any term in a
user's local denylist, exempting documentation domains and reserved fictional phone
numbers. It runs as a pre-commit hook and again in CI on every push and pull request, so a
mistake that puts personal data into a commit is caught by an automated check rather than a
careful reviewer. The health check (`tools/doctor.py`) verifies both halves of that
machinery — that the hook is actually wired in this clone, and that every required line is
still present in `.gitignore` — because both are silent failures with loud consequences.

The guard's limits are part of the design rather than an oversight: it reads the tracked
tree, not history; it cannot know which company names matter to a given person beyond what
they put in their denylist; and output directories pointed outside the repo are outside its
reach entirely. It is a backstop for the gitignore boundary, not a substitute for it.

## Non-goals

job-radar does not auto-apply to postings, ever. It does not auto-send outreach messages,
follow-ups, or anything else on a person's behalf. It does not edit the judgment layer on
its own — calibration proposes, a human applies. And it does not call an LLM anywhere
inside `engine/`: narrowing and scoring stay deterministic, and every generative step lives
in its own explicit, human-triggered stage, never folded silently into the radar itself.
