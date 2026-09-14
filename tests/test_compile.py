"""compile_pdf() — the thin wrapper around `typst compile`. Real-typst tests
are skipped when the binary isn't on PATH; the missing-binary path is faked
via monkeypatched shutil.which so it runs everywhere, including CI stages
without typst installed.
"""
import shutil

import pytest

from engine.draft import compile as compile_mod
from tests.fixtures_typst import BROKEN_TYP, MINIMAL_TYP

pytestmark_no_typst = pytest.mark.skipif(
    shutil.which("typst") is None, reason="typst binary not installed")


@pytestmark_no_typst
def test_compiles_a_minimal_document_to_pdf(tmp_path):
    src = tmp_path / "minimal.typ"
    src.write_text(MINIMAL_TYP)
    out = tmp_path / "minimal.pdf"

    ok, log = compile_mod.compile_pdf(src, out=out)

    assert ok is True
    assert out.exists()


@pytestmark_no_typst
def test_broken_document_returns_ok_false_with_a_log(tmp_path):
    src = tmp_path / "broken.typ"
    src.write_text(BROKEN_TYP)
    out = tmp_path / "broken.pdf"

    ok, log = compile_mod.compile_pdf(src, out=out)

    assert ok is False
    assert log
    assert "error" in log.lower()


@pytestmark_no_typst
def test_out_defaults_to_src_with_pdf_suffix(tmp_path):
    src = tmp_path / "minimal.typ"
    src.write_text(MINIMAL_TYP)

    ok, log = compile_mod.compile_pdf(src)

    assert ok is True
    assert (tmp_path / "minimal.pdf").exists()


def test_missing_binary_raises_filenotfounderror_naming_brew_install(
        tmp_path, monkeypatch):
    monkeypatch.setattr(compile_mod.shutil, "which", lambda name: None)
    src = tmp_path / "minimal.typ"
    src.write_text(MINIMAL_TYP)

    with pytest.raises(FileNotFoundError, match="brew install typst"):
        compile_mod.compile_pdf(src)
