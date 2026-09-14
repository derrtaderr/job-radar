"""ats_check — jd_keywords/coverage/garbled (pure text functions), ats_report
(contact hard-fail + garble hard-fail + info-only keyword gaps), and the CLI.
Pure-text cases run with no typst dependency; PDF-backed cases compile the
existing resume fixture into tmp_path and are skipped when typst isn't on
PATH, matching tests/test_verify_pdf.py's pattern. No repo-tree writes.
"""
import shutil
import subprocess
import sys

import pytest

from engine.draft.compile import compile_pdf
from tools import ats_check

pytestmark_no_typst = pytest.mark.skipif(
    shutil.which("typst") is None, reason="typst binary not installed")

RESUME_FIXTURE = "tests/fixtures/resume_example.typ"

SYNTHETIC_JD = """
We are looking for a Senior Backend Engineer with strong Python experience.
You will work with our team to build scalable Python and Kubernetes services.
Deep Kubernetes knowledge is required for daily deployments and operations.
Terraform experience is a plus but not required. The role requires strong
communication skills and the ability to mentor other engineers.
"""


# ---------------------------------------------------------------------------
# jd_keywords
# ---------------------------------------------------------------------------

def test_jd_keywords_keeps_a_tech_term_seen_twice():
    keywords = ats_check.jd_keywords(SYNTHETIC_JD)

    assert "python" in keywords


def test_jd_keywords_drops_a_stopword_even_at_high_frequency():
    keywords = ats_check.jd_keywords(SYNTHETIC_JD)

    assert "the" not in keywords
    assert "with" not in keywords
    assert "experience" not in keywords


def test_jd_keywords_drops_a_term_seen_only_once():
    keywords = ats_check.jd_keywords(SYNTHETIC_JD)

    assert "terraform" not in keywords


def test_jd_keywords_orders_by_frequency_descending():
    jd = "Docker Docker Docker Redis Redis Python Python"
    keywords = ats_check.jd_keywords(jd)

    assert keywords == ["docker", "redis", "python"]


def test_jd_keywords_counts_sentence_final_and_mid_sentence_occurrences_together():
    # A trailing sentence period must not fork "kubernetes." and "kubernetes"
    # into separate tokens — this is the structural failure mode on real JD
    # prose, where a term equally often lands mid-sentence and sentence-final.
    jd = ("We need Kubernetes experience across the platform team. "
          "Deep Kubernetes.")

    keywords = ats_check.jd_keywords(jd)

    assert "kubernetes" in keywords


def test_jd_keywords_preserves_embedded_dots_like_node_js():
    jd = "We ship Node.js services daily. Our whole backend runs Node.js."

    keywords = ats_check.jd_keywords(jd)

    assert "node.js" in keywords


def test_jd_keywords_drops_a_token_that_is_too_short_after_stripping_trailing_dots():
    jd = "This role touches AI. Some AI."

    keywords = ats_check.jd_keywords(jd)

    assert "ai" not in keywords


def test_jd_keywords_respects_max_terms_cap():
    jd = " ".join(f"{term} {term}" for term in
                   ["alpha", "bravo", "charlie", "delta", "echo"])

    keywords = ats_check.jd_keywords(jd, max_terms=2)

    assert len(keywords) == 2


# ---------------------------------------------------------------------------
# coverage
# ---------------------------------------------------------------------------

def test_coverage_splits_hits_and_gaps_case_insensitively():
    resume_text = "Built services in Python and Django for six years."
    keywords = ["python", "django", "kubernetes"]

    hits, gaps = ats_check.coverage(resume_text, keywords)

    assert hits == ["python", "django"]
    assert gaps == ["kubernetes"]


def test_coverage_returns_empty_gaps_when_everything_hits():
    resume_text = "Python and Kubernetes experience throughout."
    keywords = ["python", "kubernetes"]

    hits, gaps = ats_check.coverage(resume_text, keywords)

    assert hits == ["python", "kubernetes"]
    assert gaps == []


# ---------------------------------------------------------------------------
# garbled
# ---------------------------------------------------------------------------

def test_garbled_flags_text_shorter_than_200_chars():
    assert ats_check.garbled("too short") is not None


def test_garbled_flags_text_dominated_by_non_standard_characters():
    junk = "�\x01\x02\x03\x04\x05\x06\x07" * 30
    assert len(junk) >= 200

    assert ats_check.garbled(junk) is not None


def test_garbled_returns_none_for_clean_ascii_text():
    clean = ("Senior Data Engineer with six years building pipelines that "
              "turn raw event streams into trustworthy tables analysts "
              "actually use, end to end. ") * 2
    assert len(clean) >= 200

    assert ats_check.garbled(clean) is None


def test_garbled_allows_curly_quotes_and_dashes():
    clean = ("It's a team that's shipped — end-to-end — for years, using "
              "“curly quotes” and an em dash consistently. ") * 3
    assert len(clean) >= 200

    assert ats_check.garbled(clean) is None


def test_garbled_allows_fi_fl_ligature_codepoints():
    # Typst's Libertinus fonts can extract these ligatures in the text
    # layer; a clean resume must not trip the garble check on them.
    ligature_text = "ﬁ" * 100 + "ﬂ" * 100
    assert len(ligature_text) >= 200

    assert ats_check.garbled(ligature_text) is None


# ---------------------------------------------------------------------------
# ats_report — contact + garble hard failures (pdf_text mocked, no typst dep)
# ---------------------------------------------------------------------------

def test_ats_report_hard_fails_when_a_contact_literal_is_missing(monkeypatch, tmp_path):
    clean_text = ("Senior Data Engineer with six years building pipelines "
                  "for analysts across the company end to end. ") * 3
    monkeypatch.setattr(ats_check, "pdf_text", lambda path: clean_text)

    hard_ok, report = ats_check.ats_report(
        tmp_path / "resume.pdf", SYNTHETIC_JD,
        {"email": "missing@example.net"})

    assert hard_ok is False
    assert "missing@example.net" in report


def test_ats_report_passes_contact_check_when_literal_present(monkeypatch, tmp_path):
    clean_text = ("Senior Data Engineer with six years building pipelines "
                  "for analysts across the company end to end. Reach me at "
                  "alex.rivera@example.com any time. ") * 2
    monkeypatch.setattr(ats_check, "pdf_text", lambda path: clean_text)

    hard_ok, report = ats_check.ats_report(
        tmp_path / "resume.pdf", SYNTHETIC_JD,
        {"email": "alex.rivera@example.com"})

    assert hard_ok is True


def test_ats_report_hard_fails_when_text_layer_is_garbled(monkeypatch, tmp_path):
    junk = "�\x01\x02\x03\x04\x05\x06\x07" * 30
    monkeypatch.setattr(ats_check, "pdf_text", lambda path: junk)

    hard_ok, report = ats_check.ats_report(
        tmp_path / "resume.pdf", SYNTHETIC_JD, {})

    assert hard_ok is False


def test_ats_report_never_fails_on_keyword_gaps_alone(monkeypatch, tmp_path):
    clean_text = ("Senior Data Engineer with six years building pipelines "
                  "for analysts across the company end to end. ") * 3
    monkeypatch.setattr(ats_check, "pdf_text", lambda path: clean_text)

    hard_ok, report = ats_check.ats_report(
        tmp_path / "resume.pdf", SYNTHETIC_JD, {})

    assert hard_ok is True
    assert "kubernetes" in report


def test_ats_report_includes_the_no_stuffing_line(monkeypatch, tmp_path):
    clean_text = ("Senior Data Engineer with six years building pipelines "
                  "for analysts across the company end to end. ") * 3
    monkeypatch.setattr(ats_check, "pdf_text", lambda path: clean_text)

    hard_ok, report = ats_check.ats_report(
        tmp_path / "resume.pdf", SYNTHETIC_JD, {})

    assert ("Gaps are gaps. If the profile genuinely supports one, work it "
            "in; if not, it stays visible — never stuffed.") in report


# ---------------------------------------------------------------------------
# ats_report — full report on the compiled example resume (real typst)
# ---------------------------------------------------------------------------

@pytestmark_no_typst
def test_ats_report_on_compiled_resume_fixture_is_hard_ok_with_gaps_listed(tmp_path):
    out = tmp_path / "resume.pdf"
    ok, log = compile_pdf(RESUME_FIXTURE, out=out)
    assert ok, log

    hard_ok, report = ats_check.ats_report(
        out, SYNTHETIC_JD,
        {"email": "alex.rivera@example.com", "phone": "(303) 555-0142"})

    assert hard_ok is True
    assert "kubernetes" in report
    assert "Gaps are gaps." in report


@pytestmark_no_typst
def test_ats_report_on_compiled_resume_fixture_hard_fails_on_wrong_contact(tmp_path):
    out = tmp_path / "resume.pdf"
    ok, log = compile_pdf(RESUME_FIXTURE, out=out)
    assert ok, log

    hard_ok, report = ats_check.ats_report(
        out, SYNTHETIC_JD, {"email": "wrong@example.net"})

    assert hard_ok is False
    assert "wrong@example.net" in report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@pytestmark_no_typst
def test_cli_exits_zero_and_prints_report_when_contacts_present(tmp_path):
    out = tmp_path / "resume.pdf"
    ok, log = compile_pdf(RESUME_FIXTURE, out=out)
    assert ok, log

    jd_path = tmp_path / "jd.txt"
    jd_path.write_text(SYNTHETIC_JD)

    result = subprocess.run(
        [sys.executable, "tools/ats_check.py", str(out), str(jd_path),
         "--contact", "email=alex.rivera@example.com",
         "--contact", "phone=(303) 555-0142"],
        capture_output=True, text=True)

    assert result.returncode == 0
    assert "kubernetes" in result.stdout


@pytestmark_no_typst
def test_cli_exits_one_when_a_contact_literal_is_missing(tmp_path):
    out = tmp_path / "resume.pdf"
    ok, log = compile_pdf(RESUME_FIXTURE, out=out)
    assert ok, log

    jd_path = tmp_path / "jd.txt"
    jd_path.write_text(SYNTHETIC_JD)

    result = subprocess.run(
        [sys.executable, "tools/ats_check.py", str(out), str(jd_path),
         "--contact", "email=wrong@example.net"],
        capture_output=True, text=True)

    assert result.returncode == 1
    assert "wrong@example.net" in result.stdout
