#!/usr/bin/env python3
"""ats_check — keyword-gap and text-layer sanity check for a compiled
resume PDF against a job description. Reuses pdf_text (tools.verify_pdf)
for extraction rather than re-implementing PDF parsing.

Two kinds of finding, and they are not the same weight. Hard failures
(exit 1): a contact literal missing from the extracted text, or the text
layer looking parser-hostile (garbled — an ATS would see nothing usable).
Keyword gaps are information only, never a failure — stuffing a resume
with JD vocabulary it doesn't earn is worse than a visible gap. The
report says so directly: "Gaps are gaps. If the profile genuinely
supports one, work it in; if not, it stays visible — never stuffed."
"""
import argparse
import re
import sys
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):
    # Running as a script (`python tools/ats_check.py ...`) rather than
    # imported as `tools.ats_check` — put the repo root on sys.path so
    # the cross-package import below resolves.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.verify_pdf import pdf_text

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#./-]{2,}")

NO_STUFFING_LINE = (
    "Gaps are gaps. If the profile genuinely supports one, work it in; "
    "if not, it stays visible — never stuffed.")

# ~80 common English words plus JD filler that would otherwise dominate
# keyword frequency without carrying any ATS signal. Exact membership is
# a judgment call — tests pin behavior via a synthetic JD, not this list.
STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "nor",
    "so", "yet", "of", "in", "on", "at", "to", "from", "by", "with",
    "about", "against", "between", "into", "through", "during", "before",
    "after", "above", "below", "up", "down", "out", "off", "over",
    "under", "again", "further", "once", "here", "there", "when",
    "where", "why", "how", "all", "any", "both", "each", "few", "more",
    "most", "other", "some", "such", "no", "not", "only", "own", "same",
    "than", "too", "very", "can", "will", "just", "should", "now", "is",
    "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "for", "you", "your", "yours", "our", "ours",
    "we", "us", "team", "work", "working", "role", "years", "year",
    "experience", "ability", "abilities", "strong", "skills", "skill",
    "plus", "benefits", "salary", "requirements", "required", "require",
    "preferred", "including", "include", "etc", "looking", "seeking",
    "join", "opportunity", "candidate", "candidates", "environment",
    "must", "ideal", "position", "company",
})

# Fraction of characters outside \t\n\x20-\x7E plus common Unicode
# punctuation that trips the garble check.
GARBLE_THRESHOLD = 0.15
NEAR_EMPTY_CHARS = 200
NEAR_EMPTY_MESSAGE = "text layer too short to assess — a parser sees nothing"

# Common Unicode punctuation a clean document layer legitimately uses,
# plus the fi/fl ligature codepoints — Typst's Libertinus fonts can
# extract these as single ligature glyphs, and a clean resume must not
# trip the garble check on them.
ALLOWED_EXTRA_CHARS = "–—‘’“”•ﬁﬂ"
ALLOWED_CODEPOINTS = (
    {0x09, 0x0A} | set(range(0x20, 0x7F))
    | {ord(ch) for ch in ALLOWED_EXTRA_CHARS})


def jd_keywords(jd_text: str, max_terms: int = 30) -> list[str]:
    tokens = [tok.lower() for tok in TOKEN_RE.findall(jd_text)]
    tokens = [tok for tok in tokens if tok not in STOP_WORDS]

    counts = Counter(tokens)
    first_seen = {}
    for index, tok in enumerate(tokens):
        first_seen.setdefault(tok, index)

    candidates = [tok for tok in counts if counts[tok] >= 2]
    candidates.sort(key=lambda tok: (-counts[tok], first_seen[tok]))

    return candidates[:max_terms]


def coverage(resume_text: str, keywords: list[str]) -> tuple[list[str], list[str]]:
    lowered = resume_text.lower()
    hits = [kw for kw in keywords if kw.lower() in lowered]
    gaps = [kw for kw in keywords if kw.lower() not in lowered]
    return hits, gaps


def garbled(text: str) -> str | None:
    if len(text) < NEAR_EMPTY_CHARS:
        return NEAR_EMPTY_MESSAGE

    bad = sum(1 for ch in text if ord(ch) not in ALLOWED_CODEPOINTS)
    fraction = bad / len(text)

    if fraction > GARBLE_THRESHOLD:
        return (f"text layer looks garbled — {fraction:.0%} of characters "
                f"are non-standard (a parser would see junk)")

    return None


def ats_report(pdf_path, jd_text: str, contact: dict[str, str]) -> tuple[bool, str]:
    text = pdf_text(pdf_path)

    contact_violations = [
        f"missing contact literal — {key}: '{value}'"
        for key, value in contact.items() if value not in text]

    garble_violation = garbled(text)

    hard_ok = not contact_violations and garble_violation is None

    keywords = jd_keywords(jd_text)
    hits, gaps = coverage(text, keywords)

    lines = ["# ATS check", ""]

    if contact_violations or garble_violation:
        lines.append("## Hard failures")
        for violation in contact_violations:
            lines.append(f"- {violation}")
        if garble_violation:
            lines.append(f"- {garble_violation}")
        lines.append("")
    else:
        lines.append("## Hard failures")
        lines.append("- none")
        lines.append("")

    lines.append("## Keyword coverage")
    lines.append(f"Hits ({len(hits)}): {', '.join(hits) if hits else 'none'}")
    lines.append(f"Gaps ({len(gaps)}): {', '.join(gaps) if gaps else 'none'}")
    lines.append("")
    lines.append(NO_STUFFING_LINE)

    return hard_ok, "\n".join(lines)


def _parse_contact_arg(raw: str) -> tuple[str, str]:
    key, sep, value = raw.partition("=")
    if not sep:
        raise argparse.ArgumentTypeError(
            f"--contact must be key=value, got: {raw!r}")
    return key, value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="ats_check",
        description="Check a resume PDF's keyword coverage against a JD "
                     "and verify its contact literals and text layer.")
    parser.add_argument("pdf_path", help="path to the compiled resume PDF")
    parser.add_argument("jd_path", help="path to the job description text")
    parser.add_argument(
        "--contact", action="append", default=[], type=_parse_contact_arg,
        metavar="KEY=VALUE",
        help="contact literal that must appear verbatim in the PDF's text "
             "layer, e.g. email=you@example.com (repeatable)")
    args = parser.parse_args(argv)

    jd_text = Path(args.jd_path).read_text()
    contact = dict(args.contact)

    hard_ok, report = ats_report(args.pdf_path, jd_text, contact)
    print(report)

    return 0 if hard_ok else 1


if __name__ == "__main__":
    sys.exit(main())
