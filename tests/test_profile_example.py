"""The example profile is a schema, not decoration — /apply reads
`config/profile.md` as the claim ledger and the drafter is only allowed to
write bullets that trace to a line in it. If the shipped example loses a
frontmatter key or a section heading, a stranger copying config.example to
config/ inherits a ledger the command can't read, and the claim gate quietly
has nothing to check against. These tests pin the shape.

Parsing is deliberately plain-text: the file is markdown with a YAML-ish
frontmatter block, and pinning it with a line scan keeps the test honest about
what a reader (human or session) actually sees. The scan itself lives in
engine/profile_schema.py, shared with tools/doctor.py check 5 — this file
pins the shipped example against that same schema, it doesn't keep its own
copy of the parsing.
"""
from pathlib import Path

from engine.profile_schema import (
    CLAIM_LEDGER_LINE,
    REQUIRED_FRONTMATTER_KEYS,
    REQUIRED_SECTIONS,
    split_frontmatter,
)

PROFILE = Path(__file__).parent.parent / "config.example" / "profile.md"


def test_frontmatter_carries_the_five_keys():
    front, _ = split_frontmatter(PROFILE.read_text())
    keys = {line.split(":", 1)[0].strip() for line in front if ":" in line}

    missing = [key for key in REQUIRED_FRONTMATTER_KEYS if key not in keys]
    assert not missing, f"profile.md frontmatter missing keys: {missing}"

    # A key with no value is the same failure as a missing key from the
    # drafter's side — it has nothing to put in the contact line.
    for line in front:
        key, _, value = line.partition(":")
        if key.strip() in REQUIRED_FRONTMATTER_KEYS:
            assert value.strip(), f"profile.md frontmatter key {key.strip()!r} has no value"


def test_body_carries_the_required_sections():
    _, body = split_frontmatter(PROFILE.read_text())
    headings = [line.strip() for line in body.splitlines() if line.startswith("## ")]

    missing = [section for section in REQUIRED_SECTIONS if section not in headings]
    assert not missing, f"profile.md missing sections: {missing}"


def test_claim_ledger_line_is_present():
    # The one line that tells a stranger what this file is FOR. /apply's claim
    # gate is unenforceable without it, so it is part of the schema.
    assert CLAIM_LEDGER_LINE in PROFILE.read_text(), (
        "profile.md must state the claim-ledger rule verbatim")
