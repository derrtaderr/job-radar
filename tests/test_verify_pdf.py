"""verify_pdf — pdf_pages/pdf_text (pypdf) and verify() page-count / must-contain
/ near-empty-text checks, plus the CLI wrapper. Real-typst tests are skipped
when the binary isn't on PATH, matching tests/test_compile.py's pattern.
"""
import shutil
import subprocess
import sys

import pytest

from engine.draft.compile import compile_pdf
from tests.fixtures_typst import MINIMAL_TYP
from tools import verify_pdf

pytestmark_no_typst = pytest.mark.skipif(
    shutil.which("typst") is None, reason="typst binary not installed")

RESUME_FIXTURE = "tests/fixtures/resume_example.typ"


@pytestmark_no_typst
def test_pdf_pages_counts_the_resume_fixture_as_one_page(tmp_path):
    out = tmp_path / "resume.pdf"
    ok, log = compile_pdf(RESUME_FIXTURE, out=out)
    assert ok, log

    assert verify_pdf.pdf_pages(out) == 1


@pytestmark_no_typst
def test_pdf_text_joins_all_pages_and_contains_fixture_content(tmp_path):
    out = tmp_path / "resume.pdf"
    ok, log = compile_pdf(RESUME_FIXTURE, out=out)
    assert ok, log

    text = verify_pdf.pdf_text(out)

    assert "Alex Rivera" in text
    assert "alex.rivera@example.com" in text


@pytestmark_no_typst
def test_verify_passes_when_within_max_pages_and_must_contain_present(tmp_path):
    out = tmp_path / "resume.pdf"
    ok, log = compile_pdf(RESUME_FIXTURE, out=out)
    assert ok, log

    violations = verify_pdf.verify(
        out, max_pages=1, must_contain=["Alex Rivera", "alex.rivera@example.com"])

    assert violations == []


@pytestmark_no_typst
def test_verify_flags_page_count_over_max_naming_both_numbers(tmp_path):
    out = tmp_path / "resume.pdf"
    ok, log = compile_pdf(RESUME_FIXTURE, out=out)
    assert ok, log

    violations = verify_pdf.verify(out, max_pages=0, must_contain=[])

    assert "1 pages > max 0" in violations


@pytestmark_no_typst
def test_verify_flags_missing_must_contain_string_by_name(tmp_path):
    out = tmp_path / "resume.pdf"
    ok, log = compile_pdf(RESUME_FIXTURE, out=out)
    assert ok, log

    violations = verify_pdf.verify(
        out, max_pages=1, must_contain=["missing@example.net"])

    assert "missing literal text: 'missing@example.net'" in violations


@pytestmark_no_typst
def test_verify_flags_near_empty_text_layer_regardless_of_page_count(tmp_path):
    src = tmp_path / "minimal.typ"
    src.write_text(MINIMAL_TYP)
    out = tmp_path / "minimal.pdf"
    ok, log = compile_pdf(src, out=out)
    assert ok, log

    violations = verify_pdf.verify(out, max_pages=5, must_contain=[])

    assert "text layer nearly empty — a parser sees nothing" in violations


@pytestmark_no_typst
def test_verify_can_return_multiple_violations_at_once(tmp_path):
    out = tmp_path / "resume.pdf"
    ok, log = compile_pdf(RESUME_FIXTURE, out=out)
    assert ok, log

    violations = verify_pdf.verify(
        out, max_pages=0, must_contain=["missing@example.net"])

    assert "1 pages > max 0" in violations
    assert "missing literal text: 'missing@example.net'" in violations
    assert len(violations) == 2


@pytestmark_no_typst
def test_cli_exits_zero_and_prints_ok_summary_when_no_violations(tmp_path):
    out = tmp_path / "resume.pdf"
    ok, log = compile_pdf(RESUME_FIXTURE, out=out)
    assert ok, log

    result = subprocess.run(
        [sys.executable, "tools/verify_pdf.py", str(out), "--max-pages", "1"],
        capture_output=True, text=True)

    assert result.returncode == 0
    assert "verify_pdf: OK (1 pages)" in result.stdout


@pytestmark_no_typst
def test_cli_exits_one_and_prints_violations_when_over_max_pages(tmp_path):
    out = tmp_path / "resume.pdf"
    ok, log = compile_pdf(RESUME_FIXTURE, out=out)
    assert ok, log

    result = subprocess.run(
        [sys.executable, "tools/verify_pdf.py", str(out), "--max-pages", "0"],
        capture_output=True, text=True)

    assert result.returncode == 1
    assert "1 pages > max 0" in result.stdout


@pytestmark_no_typst
def test_cli_checks_must_contain_and_reports_missing_string(tmp_path):
    out = tmp_path / "resume.pdf"
    ok, log = compile_pdf(RESUME_FIXTURE, out=out)
    assert ok, log

    result = subprocess.run(
        [sys.executable, "tools/verify_pdf.py", str(out),
         "--max-pages", "1", "--must-contain", "missing@example.net"],
        capture_output=True, text=True)

    assert result.returncode == 1
    assert "missing literal text: 'missing@example.net'" in result.stdout
