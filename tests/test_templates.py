"""The stock resume template — a self-contained .typ that compiles as-is
(placeholders are legal Typst content) and its filled fixture, the fictional
persona Alex Rivera. Real-typst tests are skipped when the binary isn't on
PATH.
"""
import shutil
from pathlib import Path

import pytest
from pypdf import PdfReader

from engine.draft.compile import compile_pdf

pytestmark = pytest.mark.skipif(
    shutil.which("typst") is None, reason="typst binary not installed")

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_stock_template_compiles_as_is(tmp_path):
    out = tmp_path / "resume.pdf"

    ok, log = compile_pdf(TEMPLATES_DIR / "resume.typ", out=out)

    assert ok is True, log
    assert out.exists()


def test_stock_template_headings_render_uppercase(tmp_path):
    out = tmp_path / "resume.pdf"
    compile_pdf(TEMPLATES_DIR / "resume.typ", out=out)

    text = PdfReader(out).pages[0].extract_text()

    assert "SUMMARY" in text
    assert "EXPERIENCE" in text
    assert "SKILLS" in text


def test_filled_example_compiles(tmp_path):
    out = tmp_path / "resume_example.pdf"

    ok, log = compile_pdf(FIXTURES_DIR / "resume_example.typ", out=out)

    assert ok is True, log
    assert out.exists()


def test_filled_example_is_one_or_two_pages(tmp_path):
    out = tmp_path / "resume_example.pdf"
    compile_pdf(FIXTURES_DIR / "resume_example.typ", out=out)

    reader = PdfReader(out)

    assert len(reader.pages) in (1, 2)


def test_filled_example_contains_persona_email_and_headings(tmp_path):
    out = tmp_path / "resume_example.pdf"
    compile_pdf(FIXTURES_DIR / "resume_example.typ", out=out)

    text = "".join(page.extract_text() for page in PdfReader(out).pages)

    assert "alex.rivera@example.com" in text
    assert "SUMMARY" in text
    assert "EXPERIENCE" in text
    assert "SKILLS" in text


def test_stock_cover_template_compiles_as_is(tmp_path):
    out = tmp_path / "cover.pdf"

    ok, log = compile_pdf(TEMPLATES_DIR / "cover.typ", out=out)

    assert ok is True, log
    assert out.exists()


def test_filled_cover_example_compiles(tmp_path):
    out = tmp_path / "cover_example.pdf"

    ok, log = compile_pdf(FIXTURES_DIR / "cover_example.typ", out=out)

    assert ok is True, log
    assert out.exists()


def test_filled_cover_example_is_exactly_one_page(tmp_path):
    out = tmp_path / "cover_example.pdf"
    compile_pdf(FIXTURES_DIR / "cover_example.typ", out=out)

    reader = PdfReader(out)

    assert len(reader.pages) == 1


def test_filled_cover_example_contains_signature_and_persona_name(tmp_path):
    out = tmp_path / "cover_example.pdf"
    compile_pdf(FIXTURES_DIR / "cover_example.typ", out=out)

    text = "".join(page.extract_text() for page in PdfReader(out).pages)

    assert "Sincerely" in text
    assert "Alex Rivera" in text
