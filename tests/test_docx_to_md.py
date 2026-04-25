import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "docx_to_md.py"


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def _create_docx_fixture(tmp_path: Path, stem: str = "sample") -> Path:
    pandoc = shutil.which("pandoc")
    if not pandoc:
        pytest.skip("pandoc is required for docx conversion tests")

    source_md = tmp_path / f"{stem}.md"
    source_docx = tmp_path / f"{stem}.docx"
    source_md.write_text("# Sample Title\n\nA short paragraph.\n", encoding="utf-8")

    result = subprocess.run(
        [pandoc, str(source_md), "-o", str(source_docx)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    source_md.unlink()
    return source_docx


def test_docx_to_md_help_lists_core_flags():
    result = _run_cli("--help")

    assert result.returncode == 0, result.stderr
    assert "--input" in result.stdout
    assert "--output" in result.stdout


def test_docx_to_md_writes_markdown_next_to_input_by_default(tmp_path: Path):
    source_docx = _create_docx_fixture(tmp_path, stem="default-output")

    result = _run_cli("--input", str(source_docx))

    assert result.returncode == 0, result.stderr
    output_md = tmp_path / "default-output.md"
    assert output_md.exists()
    content = output_md.read_text(encoding="utf-8")
    assert "Sample Title" in content
    assert "short paragraph" in content.lower()


def test_docx_to_md_respects_explicit_output_path(tmp_path: Path):
    source_docx = _create_docx_fixture(tmp_path, stem="custom-output")
    output_md = tmp_path / "nested" / "result.md"

    result = _run_cli("--input", str(source_docx), "--output", str(output_md))

    assert result.returncode == 0, result.stderr
    assert output_md.exists()
