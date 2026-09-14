#!/usr/bin/env python3
"""verify_pdf — checks a compiled PDF against a page budget and a set of
literal strings that must appear in its text layer. Used to gate drafted
resumes/cover letters before they go out: a document that overflows the
page limit or drops a contact detail is a silent failure a human would
otherwise only catch by opening the file.

Violations are plain-English strings a human reads directly, not codes —
the CLI just prints them.
"""
import argparse
import sys

NEAR_EMPTY_CHARS = 200
NEAR_EMPTY_MESSAGE = "text layer nearly empty — a parser sees nothing"


def pdf_pages(path) -> int:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return len(reader.pages)


def pdf_text(path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "".join(page.extract_text() or "" for page in reader.pages)


def verify(path, max_pages: int, must_contain: list[str]) -> list[str]:
    violations = []

    pages = pdf_pages(path)
    text = pdf_text(path)

    if pages > max_pages:
        violations.append(f"{pages} pages > max {max_pages}")

    if len(text) < NEAR_EMPTY_CHARS:
        violations.append(NEAR_EMPTY_MESSAGE)

    for needle in must_contain:
        if needle not in text:
            violations.append(f"missing literal text: '{needle}'")

    return violations


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="verify_pdf",
        description="Verify a compiled PDF's page count and text layer.")
    parser.add_argument("path", help="path to the PDF to verify")
    parser.add_argument(
        "--max-pages", type=int, required=True,
        help="fail if the PDF has more pages than this")
    parser.add_argument(
        "--must-contain", action="append", default=[],
        metavar="STR",
        help="literal string that must appear in the text layer "
             "(repeatable)")
    args = parser.parse_args(argv)

    violations = verify(args.path, args.max_pages, args.must_contain)

    if violations:
        for violation in violations:
            print(violation)
        return 1

    pages = pdf_pages(args.path)
    print(f"verify_pdf: OK ({pages} pages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
