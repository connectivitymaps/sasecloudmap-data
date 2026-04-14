#!/usr/bin/env -S uv run
"""Helpers for recording provider outcomes in CI workflows."""

import argparse
import json
from pathlib import Path


def build_provider_status(
    *,
    provider_name: str,
    script: str,
    output_file: str,
    refresh_outcome: str,
    output_exists: bool,
    snapshot_outcome: str,
    deploy_outcome: str,
) -> dict[str, object]:
    """Build a provider status payload from workflow step outcomes."""
    eligible = (
        refresh_outcome == "success"
        and output_exists
        and snapshot_outcome == "success"
        and deploy_outcome == "success"
    )

    reasons = []
    if refresh_outcome != "success":
        reasons.append("refresh_failed")
    elif not output_exists:
        reasons.append("output_missing")
    elif snapshot_outcome != "success":
        reasons.append("snapshot_warning")
    elif deploy_outcome != "success":
        reasons.append("dev_deploy_failed")

    return {
        "provider_name": provider_name,
        "script": script,
        "output_file": output_file,
        "refresh_outcome": refresh_outcome,
        "output_exists": output_exists,
        "snapshot_outcome": snapshot_outcome,
        "deploy_outcome": deploy_outcome,
        "eligible_for_snapshot": eligible,
        "reasons": reasons,
    }


def write_provider_status(status: dict[str, object], status_dir: Path) -> Path:
    """Write a provider status payload to disk."""
    status_dir.mkdir(parents=True, exist_ok=True)
    status_path = status_dir / f"{status['provider_name']}.json"
    status_path.write_text(json.dumps(status), encoding="utf-8")
    return status_path


def _parse_bool(value: str) -> bool:
    return value.lower() == "true"


def main() -> None:
    parser = argparse.ArgumentParser(description="Write provider CI status metadata")
    parser.add_argument("--provider-name", required=True)
    parser.add_argument("--script", required=True)
    parser.add_argument("--output-file", required=True)
    parser.add_argument("--refresh-outcome", required=True)
    parser.add_argument("--output-exists", required=True)
    parser.add_argument("--snapshot-outcome", required=True)
    parser.add_argument("--deploy-outcome", required=True)
    parser.add_argument("--status-dir", default=".provider-status")
    args = parser.parse_args()

    status = build_provider_status(
        provider_name=args.provider_name,
        script=args.script,
        output_file=args.output_file,
        refresh_outcome=args.refresh_outcome,
        output_exists=_parse_bool(args.output_exists),
        snapshot_outcome=args.snapshot_outcome,
        deploy_outcome=args.deploy_outcome,
    )
    status_path = write_provider_status(status, Path(args.status_dir))
    print(status_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
