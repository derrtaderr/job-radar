"""The README makes claims about the repo, and a claim is a promise a stranger
acts on before they know enough to catch it being wrong.

Most of the README is prose that is free to change. These tests pin the parts
whose being wrong costs a first-time reader real time:

- **the no-stuffing line, verbatim.** It is the one sentence in the README that
  states a rule the drafting side actually enforces, and it is imported from
  `tools/ats_check.py` rather than copied, so the doc and the report the tool
  prints cannot drift into two different rules. A README that paraphrases it
  softer is a README that invites keyword padding.
- **every `tools/*.py` path named in the README exists on disk.** The README is
  where a stranger gets their command lines; a path that does not resolve is a
  copy-paste that fails on their first try. This also holds the same-commit
  freshness rule from the other direction: a doc line for a tool that has not
  landed yet fails here until the commit that adds the tool.
- **the quickstart still copies the example config.** `cp -r config.example
  config` is the one command that turns a clone into something that runs;
  everything downstream of it (the doctor's config check, every `radar.py`
  invocation) assumes it happened.
- **every `.claude/commands/*.md` the README names by name exists.** The README
  advertises the slash commands as the way to use the drafting and loop halves.
  Naming one that isn't installed sends a reader to a command their session
  will not have.
- **the quickstart names the doctor, and names `/setup`.** These two are the
  whole difference between a stranger who gets a green environment before
  authoring judgment and one who edits five YAML files on a machine with no
  virtualenv. They are the ordering the doctor and `/setup` were both built to
  enforce, so the README has to point at them.
- **SETUP.md exists if the README links it.** A README link into a missing file
  is worse than no link, because the reader assumes the long-form answer exists
  and goes looking for it.

Deliberately NOT pinned: the "Status: pre-release." line. Whether this repo
accepts issues is a release decision, and a test here would make that decision
a two-file edit for no safety gain — nothing in the code depends on it.
"""
import re
from pathlib import Path

from tools.ats_check import NO_STUFFING_LINE

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"
COMMANDS = REPO_ROOT / ".claude" / "commands"

# A tools path as it is written in prose or in a command line. Bounded to the
# characters a module name can hold, so a sentence that merely mentions the
# directory ("everything under tools/") never reads as a file claim.
TOOLS_PATH_RE = re.compile(r"tools/([A-Za-z0-9_]+\.py)")

# A slash command as the README writes one: inside a backtick, lowercase. The
# leading backtick is what keeps this from matching absolute paths and URLs.
COMMAND_RE = re.compile(r"`/([a-z][a-z0-9-]*)")


def _readme() -> str:
    return README.read_text()


def test_readme_exists():
    assert README.is_file()


def test_no_stuffing_line_appears_verbatim():
    # Imported from the tool that prints it, never re-typed here.
    assert NO_STUFFING_LINE in _readme()


def test_every_tools_path_named_in_the_readme_exists():
    named = sorted(set(TOOLS_PATH_RE.findall(_readme())))
    assert named, "the README names no tools/*.py path at all"
    missing = [name for name in named if not (REPO_ROOT / "tools" / name).is_file()]
    assert missing == [], f"README names tools/ files that do not exist: {missing}"


def test_quickstart_copies_the_example_config():
    assert "cp -r config.example config" in _readme()


def test_every_slash_command_named_in_the_readme_exists():
    named = sorted(set(COMMAND_RE.findall(_readme())))
    assert named, "the README names no slash command at all"
    missing = [name for name in named if not (COMMANDS / f"{name}.md").is_file()]
    assert missing == [], f"README names commands with no doc: {missing}"


def test_quickstart_names_the_doctor():
    # The environment check runs before any config work. A quickstart that
    # skips it hands a stranger their first failure at the end of an hour of
    # authoring instead of the start.
    assert "tools/doctor.py" in _readme()


def test_readme_points_at_setup_the_command():
    assert "`/setup`" in _readme()


def test_setup_md_exists_if_the_readme_links_it():
    if "SETUP.md" in _readme():
        assert (REPO_ROOT / "SETUP.md").is_file()
