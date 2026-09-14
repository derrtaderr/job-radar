"""The loop command docs carry the sentences the loop depends on.

`/outcome` and `/followup` are prose, not code, so nothing else in this
suite can notice when a rewrite quietly drops the one line that was doing
the safety work. These tests pin the load-bearing sentences — the ones
whose absence changes what the command DOES, not how it reads:

- the follow-up cap counts drafts rather than sends (drop it and a future
  editor "fixes" the cap to count sends, which uncaps it in practice, since
  nothing here ever sends);
- follow-ups are drafted and never sent (the whole command is a drafting
  step; a reader who misses this looks for a send flag that must not exist);
- a close suggests a calibration run (the only thing that closes the loop
  from outcomes back to the judgment in config/);
- the carry-forward lesson comes from the human (drop it and the command
  starts generating plausible wisdom into a permanent record);
- offers and hires are recorded only on an explicit word (the one place a
  wrong guess is later read back by a calibration run as fact);
- archiving happens before the tracker move (the ordering that makes a
  half-failed record recoverable);
- both docs open with the repo-root + `.venv/bin/python` preamble, the same
  as /apply and /add-template — every snippet in them assumes it.

A test that pins prose is a tradeoff: it makes rewording these five
sentences a deliberate two-file edit. That is the point. Everything else in
both docs is free to change without touching this file.
"""
from pathlib import Path

COMMANDS = Path(__file__).resolve().parent.parent / ".claude" / "commands"

PREAMBLE = ("**Every command in this file runs from the repo root, using "
            "`.venv/bin/python`.**")


def _doc(name: str) -> str:
    return (COMMANDS / name).read_text()


def test_outcome_doc_exists():
    assert (COMMANDS / "outcome.md").is_file()


def test_followup_doc_exists():
    assert (COMMANDS / "followup.md").is_file()


def test_followup_cap_counts_drafts_not_sends():
    assert "The cap counts drafts, not sends" in _doc("followup.md")


def test_followup_never_sends_anything():
    assert "This command never sends anything." in _doc("followup.md")


def test_outcome_suggests_a_calibration_run_on_every_close():
    assert "Every move into Closed ends by suggesting a calibrate run." in _doc(
        "outcome.md")


def test_outcome_archives_before_it_edits_the_tracker():
    assert "Archive first, then move the tracker row." in _doc("outcome.md")


def test_outcome_makes_the_human_supply_the_carry_forward_lesson():
    assert ("The human supplies the carry-forward lesson. Ask for it; do not "
            "write one.") in _doc("outcome.md")


def test_outcome_records_offers_only_on_an_explicit_word():
    assert "get recorded only on the human's explicit word." in _doc("outcome.md")


def test_both_docs_carry_the_repo_root_preamble():
    for name in ("outcome.md", "followup.md"):
        assert PREAMBLE in _doc(name), name
