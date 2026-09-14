"""Thin wrapper around the `typst` CLI — compiles a .typ source to PDF and
never raises on a compile failure (a broken document is a normal outcome the
caller inspects via the returned ok flag and log), only on the binary itself
being absent, which is an environment problem the caller can't recover from."""
import shutil
import subprocess
from pathlib import Path


def compile_pdf(src: Path, out: Path | None = None) -> tuple[bool, str]:
    if shutil.which("typst") is None:
        raise FileNotFoundError(
            "typst binary not found on PATH — install it with `brew install typst`")

    src = Path(src)
    out = Path(out) if out is not None else src.with_suffix(".pdf")

    result = subprocess.run(
        ["typst", "compile", str(src), str(out)],
        capture_output=True, text=True)

    log = result.stdout + result.stderr
    return result.returncode == 0, log
