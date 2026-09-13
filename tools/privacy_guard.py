#!/usr/bin/env python3
"""Privacy guard — fails the commit/build when tracked files carry personal data.
Patterns are deliberately conservative: an email or phone in a tracked file is
always a bug in this repo (personal data belongs in gitignored config/)."""
import re
import subprocess
import sys
from pathlib import Path

EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[a-z]{2,}\b", re.I)
PHONE = re.compile(r"(?<![\d.:/-])(?:\(\d{3}\)\s?|\d{3}[-.\s])\d{3}[-.\s]\d{4}(?![\d.])")
SKIP_SUFFIXES = {".png", ".jpg", ".gif", ".pdf", ".woff", ".woff2", ".ico"}
# Exact relative paths (as reported by `git ls-files`), never a bare basename —
# a basename match would let ANY file named e.g. test_privacy_guard.py
# anywhere in the tree bypass the guard. tests/test_privacy_guard.py needs
# this because it deliberately carries one non-placeholder fixture
# (test_real_looking_email_still_caught) to prove the carve-out below can't
# over-exempt; everything else it uses is a reserved placeholder and needs
# no exemption at all.
SKIP_FILES = {".privacy-denylist.example", "tests/test_privacy_guard.py"}

# RFC 2606 reserves these domains for documentation — never a real address.
RESERVED_EMAIL_DOMAINS = {"example.com", "example.org", "example.net"}


def _is_reserved_domain(email):
    domain = email.rsplit("@", 1)[-1].lower()
    return domain in RESERVED_EMAIL_DOMAINS


def _is_nanp_fictional(phone):
    # NANP reserves NPA-555-01XX as the official "this is fake" phone range.
    digits = re.sub(r"\D", "", phone)
    if len(digits) != 10:
        return False
    exchange, line = digits[3:6], digits[6:]
    return exchange == "555" and line[:2] == "01"


def scan_text(text, denylist):
    hits = []
    for m in EMAIL.finditer(text):
        if not _is_reserved_domain(m.group(0)):
            hits.append(f"email: {m.group(0)}")
    for m in PHONE.finditer(text):
        if not _is_nanp_fictional(m.group(0)):
            hits.append(f"phone: {m.group(0)}")
    low = text.lower()
    for term in denylist:
        if term and term.lower() in low:
            hits.append(f"denylist: {term}")
    return hits

def scan_repo(root="."):
    root = Path(root)
    denypath = root / ".privacy-denylist"
    denylist = [l.strip() for l in denypath.read_text().splitlines()
                if l.strip() and not l.startswith("#")] if denypath.exists() else []
    tracked = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True,
                             text=True, check=True).stdout.splitlines()
    violations = []
    for rel in tracked:
        p = root / rel
        if p.suffix in SKIP_SUFFIXES or rel in SKIP_FILES or not p.exists():
            continue
        for hit in scan_text(p.read_text(errors="replace"), denylist):
            violations.append(f"{rel}: {hit}")
    return violations

if __name__ == "__main__":
    v = scan_repo()
    for line in v:
        print(f"PRIVACY GUARD: {line}")
    sys.exit(1 if v else 0)
