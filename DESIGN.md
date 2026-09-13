# job-radar: design and boundaries

## What this is

job-radar is a deterministic job-search radar. It scrapes fresh postings from public job
boards, runs them through a set of standing kill rules, scores whatever survives, and hands
back a ranked queue meant to be read inside a Claude Code session. Nothing about matching or
ranking is generative. A posting either trips a rule or it doesn't, and every rejection quotes
the exact line of the posting that triggered it, so a human can check the engine's homework in
seconds instead of trusting a black box.

The near-term scope is sourcing and triage: pull postings, kill the obvious no-fits, score and
rank the rest. Later phases build outward from that ranked queue without changing how it's
produced. A Typst-based drafting pipeline turns a ranked posting into an application draft. An
outcome tracker records what happened after each application (screen, rejection, silence).
Follow-up surfacing resurfaces applications that have gone quiet past a threshold. Outcome to
rule calibration closes the loop by looking at which kills correlated with the outcomes a
person actually cared about, and proposing rule adjustments rather than changing scores by
hand.

## Two-layer architecture

The repo is split into a generic layer and a personal layer, and the split is structural, not
a convention someone has to remember.

`engine/` holds all of the code: scrapers, the kill-rule evaluator, the scorer, the queue
builder. This code has no opinions about any specific person's job search. It reads
configuration and produces output; it does not encode anyone's preferences directly.

`config/` holds the judgment layer: the actual kill rules, scoring weights, target roles,
excluded companies, and any other preference that reflects one person's search. This directory
is gitignored in its entirety. It never enters version control, and the engine is written so
that it cannot run meaningfully without a config directory being supplied at runtime, forcing
every user to bring their own.

`config.example/` is checked in and ships with the repo. It contains a complete, working
configuration for a fictional persona; no real employer, person, or search criteria appears in
it. Its job is to make the repo runnable and legible to a stranger on first clone, and to
document the shape config files take without leaking anyone's actual preferences.

## Thesis: deterministic rules, judgment stays with the human

The engine makes no calls to a language model, on principle, not as a temporary limitation.
Deterministic rules are reproducible: the same posting run through the same config always
produces the same kill or the same score, which means the rules can be tuned, versioned, and
debugged like any other code. An LLM-based filter would trade that reproducibility for fuzzy
judgment at exactly the point where the cost of a wrong call (silently dropping a posting a
person would have wanted) is highest and hardest to detect.

Judgment still happens, just later and by a human, on the ranked report the engine produces
inside a Claude Code session. That's the intended second stage: the engine narrows a large,
noisy stream of postings down to a small, evidenced list; a person (assisted by an LLM session
reading that list, if they choose) makes the actual calls. Every kill is overrulable, because
every kill is visible: it names the rule that fired and quotes the line of the posting that
matched it, so overriding it is a one-line decision, not an archaeology project.

## Privacy model

Nothing about a real person's job search belongs in this repository's version-controlled
history. Personal data — target roles, salary floors, excluded employers, notes on specific
postings, resumes, application state — lives exclusively in `config/`, which is gitignored
from the first commit onward. The engine reads from that directory at runtime but never writes
example data into it, and no code path serializes personal config back into a tracked file.

A CI privacy guard runs on every push and pull request. It scans the diff for anything that
looks like it originated in `config/` (paths, and telltale key names that only appear in a
populated config) and fails the build if it finds one, so a mistake that puts personal data
into a commit gets caught by an automated check rather than a careful reviewer.

## Non-goals

job-radar does not auto-apply to postings, ever. It does not auto-send outreach messages,
follow-ups, or anything else on a person's behalf. And it does not call an LLM anywhere inside
`engine/` — narrowing and scoring stay deterministic, and any generative step (like drafting)
lives in its own explicit, human-triggered stage, never folded silently into the radar itself.
