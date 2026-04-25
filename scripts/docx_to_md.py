"""Convert a Word .docx file into Markdown via pandoc.

Usage:
    uv run python scripts/docx_to_md.py --input path/to/file.docx
    uv run python scripts/docx_to_md.py --input path/to/file.docx --output path/to/file.md
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
from pathlib import Path


LOGGER = logging.getLogger("docx_to_md")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert a Word .docx file into Markdown via pandoc.",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to the source .docx file.",
    )
    parser.add_argument(
        "--output",
        help="Optional output .md path. Defaults to the input filename with a .md suffix.",
    )
    return parser


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


def resolve_output_path(input_path: Path, output_arg: str | None) -> Path:
    if output_arg:
        return Path(output_arg).expanduser().resolve()
    return input_path.with_suffix(".md")


def require_pandoc() -> str:
    pandoc = shutil.which("pandoc")
    if pandoc:
        return pandoc
    raise RuntimeError(
        "pandoc is not available on PATH. Install pandoc first, then rerun this command."
    )


def validate_input_path(input_arg: str) -> Path:
    input_path = Path(input_arg).expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input file does not exist: {input_path}")
    if not input_path.is_file():
        raise RuntimeError(f"Input path is not a file: {input_path}")
    if input_path.suffix.lower() != ".docx":
        raise RuntimeError(f"Only .docx files are supported: {input_path}")
    return input_path


def run_pandoc(pandoc: str, input_path: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [pandoc, str(input_path), "-t", "gfm", "-o", str(output_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or "pandoc failed without stderr output"
        raise RuntimeError(f"pandoc conversion failed: {stderr}")


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        input_path = validate_input_path(args.input)
        output_path = resolve_output_path(input_path, args.output)
        pandoc = require_pandoc()
        run_pandoc(pandoc, input_path, output_path)
    except Exception as exc:
        LOGGER.error("%s", exc)
        return 1

    LOGGER.info("Converted %s -> %s", input_path, output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
