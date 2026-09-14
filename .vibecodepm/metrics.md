---
name: job-radar metrics
read_by: the Phase 4 ship-check / stranger-walk audit before any release or visibility decision, and any session changing radar.py's first-run output, the doctor's checks, or /outcome's archive step
milestone: Phase 4 (offline demo + ship-check contract files)
status: current — matches the build at lane/phase-4
date: 2026-09-13
supersedes: none — first metrics file for this repo
---

# Metrics — job-radar

## The activation event

**A user completes `/setup` (or hand-edits `config/`) and `python radar.py` writes their
first `radar-out/<date>/queue.md`.**

Measured by two conditions holding together: the doctor reports clean (their config genuinely
loads — nine checks, WARN never blocks) AND a day folder exists on disk afterward (the run
produced real output, not just an exit code). Neither alone is activation. A clean doctor
with no run yet is a stranger who set up correctly and stopped; a day folder with a dirty
doctor can't happen — `radar.py` refuses to run at all on a config that doesn't load.

**Why this is the right moment, not `tools/doctor.py` going green on its own.** A green
doctor proves the config loads. It says nothing about whether the rules IN it are any good,
and it produces nothing the user can look at and judge. The queue is the first artifact this
system hands back — a ranked table with kills quoted, not swallowed — and it is the first
point where a user can tell whether the tool is worth trusting with their real search. Before
that, everything is setup.

**Why it isn't `/apply` or a compiled PDF.** Drafting is depth, and it needs typst installed
— a real dependency, not a formality. Making activation depend on it would measure "did this
user's machine have typst" as much as "did the radar produce something worth reading," and a
build whose activation event silently gates on an optional binary is measuring the wrong
thing. The queue is reachable by every user; the resume/cover letter path is reachable by
most of them, one `brew install` later.

**Why the offline demo (Phase 5, `tools/demo.py`) does NOT become the activation event.**
The demo produces the same shape of artifact — a queue.md, in fact — but over fictional data
before the user has written a line of their own judgment. It proves the CODE works, which is
a different claim from "this user's search is running." Moving activation onto the demo
would let a build ship where every demo runs clean while the real setup path (six config
files, a profile, a claim ledger) silently regressed. The demo gets its own row below instead
— it is the moment a stranger decides the repo is worth the setup cost, one step before the
activation event proper, and conflating the two would stop measuring either honestly.

### How it is measured

No telemetry, no hosted component, no accounts — by design, per the README's privacy model
(nothing about a real search leaves the user's machine). So activation isn't measured by
instrumenting a user; it's measured by making it structurally impossible to ship a build
where the activation path is broken, and the instrumentation lives in the test suite.

| What has to be true for activation | What proves it | Where |
|---|---|---|
| The doctor genuinely reports clean on a valid config | All nine checks OK, exit 0 | `tests/test_doctor.py::test_cli_prints_one_line_per_check_and_exits_0_when_all_ok` |
| A WARN (missing typst/jobspy) never blocks activation | WARN present, exit code still 0 | `tests/test_doctor.py::test_cli_warn_never_flips_the_exit_code` |
| `radar.py` genuinely refuses to run on no config, naming the fix | Exit non-zero, output names `config.example` | `tests/test_entrypoint.py::test_entry_point_exits_nonzero_on_a_missing_config` |
| A real run writes the day folder AND saves state | `radar-out/<date>/queue.md` exists; state.json updated | `tests/test_cli.py::test_run_writes_the_day_folder_and_saves_state` |
| The entry point itself works from a fresh clone, not just the library underneath it | Subprocess dry-run from repo root, exit 0 | `tests/test_entrypoint.py::test_entry_point_runs_a_dry_run_from_the_repo_root` |
| The shipped example config IS a config that loads and activates | `config.example` loads via the real loader, dry-run succeeds | `tests/test_profile_example.py`, `tests/test_config.py` |
| Kills are visible, not swallowed, in the artifact the user reads | queue.md renders the kill list with quoted evidence under every survivor table | `tests/test_report.py` |

### The demo, named separately (not activation, but adjacent to it)

| What has to be true | What proves it | Where |
|---|---|---|
| A stranger with zero config sees the whole system run | `tools/demo.py` exits 0 from a fresh clone, no `config/` required | `tests/test_demo.py::test_exits_zero`, `tests/test_demo.py::test_cli_subprocess_runs_clean_from_the_repo_root` |
| It never touches the user's real config or state | Loads `config.example` explicitly, copied into `--out`; nothing outside `--out` is written | `tools/demo.py` docstring + `tests/test_demo.py` (all cases pass `--out` under `tmp_path`) |
| It reproduces, so a broken build fails a test rather than "looking flaky" in someone's hands | Two runs (different dirs, and a same-dir rerun) produce byte-identical text artifacts | `tests/test_demo.py::test_two_runs_into_two_dirs_produce_identical_text_artifacts`, `::test_rerun_into_the_same_directory_reproduces_the_queue` |
| A machine with no typst still completes, with the gap named rather than a traceback | Exit 0, printed note naming typst, no half-written `drafting/` directory | `tests/test_demo.py::test_without_typst_prints_a_note_and_still_exits_zero` |

## Secondary metric: first `/outcome` recorded

**A user archives their first application** — `/outcome` copies the `apply-out/` folder into
`archive_dir` and writes `outcome.md`, then moves the tracker row.

This is secondary, not primary, because it depends on the user having applied to something
real, which depends on judgment this tool cannot supply (whether to actually send the
application) and often takes days after activation, not minutes. It matters because it is the
first point where the LOOP half of the system (the third subsystem, calibration) has anything
to work with at all — a calibration report over zero archived applications is not a rough
report, it's an empty one.

| What has to be true | What proves it | Where |
|---|---|---|
| Archiving actually files everything the apply step produced | `archive_application` copies resume/cover sources, PDFs, and the JD, all-or-nothing | `tests/test_archive.py::test_archive_application_copies_all_files` |
| The archived record seeds correctly, with a dated log line | `outcome.md` frontmatter + `## Log` seeded with "applied" | `tests/test_archive.py::test_archive_application_seeds_log_with_applied_line` |
| The chain composes end to end against a real tracker move | Archive → move Drafted→Active→Closed → `tracker_check` still passes | `tests/test_loop_e2e.py::TestLoopChain` (stages 3, 4, 8) |

**Rough, and named as such.** There is no count of "how many users have recorded a first
outcome" anywhere — no telemetry exists to produce one, by the same privacy-model decision
that shapes the primary metric above. This row proves the MECHANISM works, not that any
particular user has used it. Closing that gap would mean adding telemetry to a tool whose
entire pitch is that nothing about a real search leaves the user's machine, which is not a
gap this milestone proposes to close.
