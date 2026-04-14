#!/usr/bin/env -S uv run
"""Validate snapshot drift for a single provider output file."""

import argparse
from pathlib import Path

from dotenv import load_dotenv

from provider_data.utils.validate_snapshot import validate


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate snapshot drift for a single provider output file"
    )
    parser.add_argument("--expected-file", required=True)
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--threshold", type=float, default=10.0)
    args = parser.parse_args()

    load_dotenv()
    warnings = validate(
        Path(args.output_dir),
        threshold=args.threshold,
        expected_files={args.expected_file},
    )
    if warnings:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
