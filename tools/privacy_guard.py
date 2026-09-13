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
SKIP_FILES = {".privacy-denylist.example", "test_privacy_guard.py"}

def scan_text(text, denylist):
    hits = []
    for m in EMAIL.finditer(text):
        hits.append(f"email: {m.group(0)}")
    for m in PHONE.finditer(text):
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
        if p.suffix in SKIP_SUFFIXES or p.name in SKIP_FILES or not p.exists():
            continue
        for hit in scan_text(p.read_text(errors="replace"), denylist):
            violations.append(f"{rel}: {hit}")
    return violations

if __name__ == "__main__":
    v = scan_repo()
    for line in v:
        print(f"PRIVACY GUARD: {line}")
    sys.exit(1 if v else 0)
