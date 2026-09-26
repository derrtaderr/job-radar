"""Content fingerprints — two per posting, so the same req arriving twice under
two ids can be recognised across days.

Suppression keys on company plus URL, which both change when a req is reissued
or reposted. Two shapes of that miss show up in live runs, and they need two
different fingerprints because neither one catches both:

- **Same req, different territory.** One posting listed as "Eastern US" and
  again as "Western US". The bodies are identical once the territory token is
  gone, so `fp_body` catches it.
- **Aggregator repost.** A job board reposts a client's req under its own name
  with the client anonymised out of the prose. The body genuinely differs, so
  `fp_body` cannot bridge it — but the comp band and the benefits block are
  copied verbatim, so `fp_comp` catches it.

A fingerprint is evidence for a FLAG, never for a suppression. The aggregator
copy sometimes carries detail the original lacks, so the run says "possible
repost of <jid>" and leaves the posting in the queue for the human.
"""
from __future__ import annotations

import hashlib
import re

from engine.radar.location import strip_territory
from engine.radar.rules_engine import body_stated_max

# The benefits block, as a set of tokens rather than as prose. A repost
# reorders and rewrites the sentence around these but rarely changes which ones
# are on offer, so a sorted set of what appears is stabler than the text.
_BENEFIT_TOKENS = {
    "401k": r"401\s?\(?k\)?",
    "dental": r"\bdental\b",
    "equity": r"\bequity\b|\bstock options\b|\brsus?\b",
    "fsa": r"\bfsa\b",
    "hsa": r"\bhsa\b",
    "life-insurance": r"\blife insurance\b",
    "medical": r"\bmedical\b|\bhealth insurance\b",
    "parental-leave": r"\bparental leave\b|\bmaternity leave\b",
    "pto": r"\bpto\b|\bpaid time off\b",
    "stipend": r"\b(?:home ?office|remote|wellness) stipend\b",
    "vision": r"\bvision\b",
}
_BENEFIT_RES = {name: re.compile(pattern, re.I)
                for name, pattern in _BENEFIT_TOKENS.items()}

_NON_WORD = re.compile(r"[^a-z0-9]+")


def _digest(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:16]


def _collapse(text: str) -> str:
    """Lower-cased, every run of non-alphanumerics flattened to one space. Two
    postings that differ only in punctuation, casing or line wrapping are the
    same posting, and a scrape re-wraps prose constantly."""
    return _NON_WORD.sub(" ", str(text or "").lower()).strip()


def benefit_tokens(text) -> tuple:
    """The benefits on offer in a posting body, as a sorted tuple of names.
    Sorted so the order they were listed in cannot change the fingerprint."""
    body = str(text or "")
    return tuple(sorted(name for name, rx in _BENEFIT_RES.items() if rx.search(body)))


def _comp_band(row: dict):
    """The comp band as a comparable string, or None when the posting states
    none. Falls back to the largest band stated in the prose, which is what a
    posting with no structured amounts still gives a reader."""
    lo, hi = row.get("min_amount"), row.get("max_amount")
    if lo or hi:
        interval = str(row.get("interval") or "yearly").lower()
        return f"{lo or ''}-{hi or ''}-{interval}"
    stated = body_stated_max(row.get("description"))
    return f"stated-{stated}" if stated is not None else None


def fp_comp(row: dict):
    """Comp band plus benefits block, or None when the posting carries neither.

    None rather than a hash of emptiness: a fingerprint of nothing would match
    every thin posting to every other thin posting, which is the false merge
    this mechanism exists to prevent rather than to cause.
    """
    band = _comp_band(row)
    benefits = benefit_tokens(row.get("description"))
    if band is None and not benefits:
        return None
    return _digest(f"{band or 'no-band'}|{','.join(benefits)}")


def _without_company(text: str, company) -> str:
    """The text with the employer's own name removed. It is the one token
    guaranteed to differ between an original and an aggregator's repost."""
    name = str(company or "").strip()
    if len(name) < 4:
        return text
    return re.sub(re.escape(name), " ", text, flags=re.I)


def fp_body(row: dict):
    """Title plus body, with the territory tokens and the company's own name
    stripped, or None when the posting has no body to fingerprint.

    Title is included because one company reposting a DIFFERENT role with the
    same boilerplate body is not a repost of the first one.
    """
    description = str(row.get("description") or "")
    if not description.strip():
        return None
    body = strip_territory(_without_company(description, row.get("company")))
    title = strip_territory(_without_company(str(row.get("title") or ""),
                                            row.get("company")))
    return _digest(f"{_collapse(title)}|{_collapse(body)}")


def fp_equal(a, b) -> bool:
    """Do two fingerprints match?

    False whenever either side is unknown. A legacy state entry has no
    fingerprints, and if None matched None every posting recorded before this
    mechanism existed would read as a repost of every other one.
    """
    return a is not None and b is not None and a == b
