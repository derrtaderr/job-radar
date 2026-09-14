"""Profile schema — the shape `profile.md` must have for /apply's claim gate
to work: five frontmatter keys, five section headings, and the claim-ledger
sentence that tells a stranger what the file is for.

Shared by two readers that must never drift apart: tests/test_profile_example.py
(pins the shipped config.example/profile.md) and tools/doctor.py check 6
(validates whatever profile.md a person actually wrote in their own config/).
One schema, read by both, never copied — a copy is exactly how the example
and the doctor's idea of "valid" would quietly diverge.
"""
from __future__ import annotations

REQUIRED_FRONTMATTER_KEYS = ("name", "email", "phone", "location", "links")
REQUIRED_SECTIONS = (
    "## Summary",
    "## Experience",
    "## Skills",
    "## Education",
    "## Evidence notes",
)
CLAIM_LEDGER_LINE = (
    "This file is the CLAIM LEDGER. The drafter may only write resume claims "
    "that trace to a line here.")


class ProfileSchemaError(Exception):
    """Raised when profile.md doesn't even open/close its frontmatter fence —
    a shape so broken that per-key checks can't run at all."""


def split_frontmatter(text: str) -> tuple[list[str], str]:
    """Return (frontmatter lines, body). Raises ProfileSchemaError if the
    file doesn't open with a '---' fenced block or never closes it."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ProfileSchemaError("profile.md must open with a '---' frontmatter fence")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return lines[1:index], "\n".join(lines[index + 1:])
    raise ProfileSchemaError("profile.md frontmatter block is never closed with '---'")


def check_profile(text: str) -> list[str]:
    """Validate a profile.md's shape against the claim-ledger schema. Returns
    plain-English violation strings a human reads directly — empty list means
    valid. Same convention as engine/loop/tracker_schema.py::tracker_check."""
    try:
        front, body = split_frontmatter(text)
    except ProfileSchemaError as exc:
        return [str(exc)]

    violations = []

    keys = {line.split(":", 1)[0].strip() for line in front if ":" in line}
    missing = [key for key in REQUIRED_FRONTMATTER_KEYS if key not in keys]
    if missing:
        violations.append(f"profile.md frontmatter missing keys: {missing}")

    # A key with no value is the same failure as a missing key from the
    # drafter's side — it has nothing to put in the contact line.
    for line in front:
        key, _, value = line.partition(":")
        if key.strip() in REQUIRED_FRONTMATTER_KEYS and not value.strip():
            violations.append(f"profile.md frontmatter key {key.strip()!r} has no value")

    headings = [line.strip() for line in body.splitlines() if line.startswith("## ")]
    missing_sections = [section for section in REQUIRED_SECTIONS if section not in headings]
    if missing_sections:
        violations.append(f"profile.md missing sections: {missing_sections}")

    # The one line that tells a stranger what this file is FOR. /apply's
    # claim gate is unenforceable without it, so it is part of the schema.
    if CLAIM_LEDGER_LINE not in text:
        violations.append("profile.md must state the claim-ledger rule verbatim")

    return violations
