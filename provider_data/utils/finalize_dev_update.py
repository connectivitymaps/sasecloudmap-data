#!/usr/bin/env -S uv run
"""Finalize the unified dev update workflow from per-provider artifacts."""

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path

from dotenv import load_dotenv

from provider_data.utils.upload_to_r2 import (
    get_s3_client,
    prepare_snapshot_upload_dir,
    upload_snapshots,
)
from provider_data.utils.validate_snapshot import (
    download_snapshot,
    get_latest_snapshot_prefix,
)


def load_provider_statuses(artifacts_dir: Path) -> dict[str, dict]:
    """Load per-provider status artifacts."""
    statuses = {}
    for status_file in sorted(artifacts_dir.glob("provider-status-*/*.json")):
        data = json.loads(status_file.read_text(encoding="utf-8"))
        statuses[data["provider_name"]] = data
    return statuses


def copy_provider_output_artifacts(
    *, expected_by_provider: dict[str, str], artifacts_dir: Path, output_dir: Path
) -> set[str]:
    """Copy eligible provider output artifacts into output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for provider_name, output_file in expected_by_provider.items():
        artifact_file = artifacts_dir / f"provider-output-{provider_name}" / output_file
        if artifact_file.exists():
            shutil.copy2(artifact_file, output_dir / output_file)
    return {path.name for path in output_dir.glob("*.json")}


def finalize_dev_update(
    *,
    expected_records: list[dict[str, str]],
    artifacts_dir: Path,
    output_dir: Path,
    timestamp: str | None = None,
) -> dict[str, object]:
    """Publish the R2 snapshot from provider job artifacts."""
    load_dotenv()

    expected_files = {record["output_file"] for record in expected_records}
    expected_by_provider = {
        record["provider_name"]: record["output_file"] for record in expected_records
    }

    statuses = load_provider_statuses(artifacts_dir)
    allowed_files = copy_provider_output_artifacts(
        expected_by_provider=expected_by_provider,
        artifacts_dir=artifacts_dir,
        output_dir=output_dir,
    )

    missing_status = sorted(
        provider_name
        for provider_name in expected_by_provider
        if provider_name not in statuses
    )
    if missing_status:
        print(
            "::warning::No provider status artifact found for: "
            + ", ".join(missing_status)
        )

    blocked = []
    eligible_providers = []
    for provider_name in sorted(expected_by_provider):
        status = statuses.get(provider_name)
        if status is None:
            blocked.append((provider_name, ["status_missing"]))
            continue
        if status["eligible_for_snapshot"]:
            eligible_providers.append(provider_name)
        else:
            blocked.append((provider_name, status["reasons"]))

    if blocked:
        for provider_name, reasons in blocked:
            print(
                "::warning::Provider excluded from fresh snapshot publication: "
                f"{provider_name} ({', '.join(reasons)})"
            )

    has_deployed = bool(allowed_files)
    missing_artifacts = sorted(
        provider_name
        for provider_name in eligible_providers
        if expected_by_provider[provider_name] not in allowed_files
    )
    if missing_artifacts:
        print(
            "::warning::Eligible providers were missing output artifacts: "
            + ", ".join(missing_artifacts)
        )

    client = get_s3_client()
    bucket = os.environ["R2_BUCKET_NAME"]
    latest_prefix = get_latest_snapshot_prefix(client, bucket)
    previous_snapshot = (
        download_snapshot(client, bucket, latest_prefix)
        if latest_prefix is not None
        else {}
    )

    with tempfile.TemporaryDirectory(prefix="r2-upload-") as temp_dir:
        staging_dir = Path(temp_dir)
        staged_current, carried_forward = prepare_snapshot_upload_dir(
            output_dir,
            staging_dir,
            allowed_files,
            expected_files=expected_files,
            previous_snapshot=previous_snapshot,
        )

        print(
            f"Prepared R2 snapshot staging dir {staging_dir} with "
            f"{len(staged_current)} refreshed and {len(carried_forward)} carried-forward files."
        )

        if staged_current or carried_forward:
            upload_snapshots(staging_dir, timestamp=timestamp)
        else:
            print("::warning::No provider data available for snapshot publication.")

    return {
        "has_deployed": has_deployed,
        "staged_current": staged_current,
        "carried_forward": carried_forward,
        "missing_status": missing_status,
        "missing_artifacts": missing_artifacts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Finalize unified dev update outputs")
    parser.add_argument("--expected-providers-json", required=True)
    parser.add_argument("--artifacts-dir", default=".artifacts")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--github-output", default=None)
    parser.add_argument("--timestamp", default=None)
    args = parser.parse_args()

    result = finalize_dev_update(
        expected_records=json.loads(args.expected_providers_json),
        artifacts_dir=Path(args.artifacts_dir),
        output_dir=Path(args.output_dir),
        timestamp=args.timestamp,
    )
    if args.github_output:
        with Path(args.github_output).open("a", encoding="utf-8") as fh:
            fh.write(f"has_deployed={'true' if result['has_deployed'] else 'false'}\n")


if __name__ == "__main__":
    main()
