"""The warm-path command docs carry the sentences the system depends on.
Same tradeoff as test_loop_docs.py: rewording these is a two-file edit, on
purpose."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMMANDS = ROOT / ".claude" / "commands"
PREAMBLE = ("**Every command in this file runs from the repo root, using "
            "`.venv/bin/python`.**")


def _doc(name):
    return (COMMANDS / name).read_text()


def test_apply_runs_the_gate_first():
    text = _doc("apply.md")
    assert "## Step 0 — Ask first if you know someone there" in text
    assert text.index("## Step 0") < text.index("## Step 1")
    assert "tools/network_cli.py gate" in text


def test_reach_never_sends_and_never_invents():
    text = _doc("reach.md")
    assert PREAMBLE in text
    assert "This command never sends anything." in text
    assert "Every claim traces to `config/profile.md`." in text
    assert 'If no build fits, say "no build fits".' in text
    assert "One touch in five is a control" in text


def test_paths_never_writes_a_failed_lookup():
    text = _doc("paths.md")
    assert PREAMBLE in text
    assert "A failed lookup writes nothing." in text


def test_outcome_records_the_applied_touch():
    assert "tools/network_cli.py touch" in _doc("outcome.md")
