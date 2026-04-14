#!/usr/bin/env -S uv run
"""Upload all output/*.json files to Cloudflare R2 with a timestamp prefix.

This creates a historical snapshot of provider data on each run.
Objects are stored as: <timestamp>/<provider>.json

Required environment variables:
    R2_ACCOUNT_ID       - Cloudflare account ID
    R2_ACCESS_KEY_ID    - R2 API token access key ID
    R2_SECRET_ACCESS_KEY - R2 API token secret access key
    R2_BUCKET_NAME      - R2 bucket name
"""

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import boto3
from dotenv import load_dotenv

LATEST_POINTER_KEY = "latest.txt"


def get_s3_client():
    """Create an S3 client configured for Cloudflare R2."""
    account_id = os.environ["R2_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def prepare_snapshot_upload_dir(
    output_dir: Path,
    staging_dir: Path,
    allowed_files: set[str],
    *,
    expected_files: set[str] | None = None,
    previous_snapshot: dict[str, dict] | None = None,
) -> tuple[list[str], list[str]]:
    """Stage upload files, carrying forward prior snapshot data for blocked providers."""
    previous_snapshot = previous_snapshot or {}
    if expected_files is None:
        expected_files = set(allowed_files)

    staged_current = []
    carried_forward = []

    staging_dir.mkdir(parents=True, exist_ok=True)

    for filename in sorted(expected_files):
        destination = staging_dir / filename

        if filename in allowed_files:
            source = output_dir / filename
            if not source.exists():
                continue
            shutil.copy2(source, destination)
            staged_current.append(filename)
            continue

        prior_data = previous_snapshot.get(filename)
        if prior_data is None:
            continue

        destination.write_text(json.dumps(prior_data), encoding="utf-8")
        carried_forward.append(filename)

    return staged_current, carried_forward


def upload_snapshots(output_dir: Path, timestamp: str | None = None):
    """Upload all JSON files from output_dir to R2 under a timestamp prefix."""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    bucket = os.environ["R2_BUCKET_NAME"]
    client = get_s3_client()

    json_files = sorted(output_dir.glob("*.json"))
    if not json_files:
        print("No JSON files found in output/")
        return

    print(f"Uploading {len(json_files)} files to R2 with prefix {timestamp}/")

    for json_file in json_files:
        key = f"{timestamp}/{json_file.name}"
        client.upload_file(
            Filename=str(json_file),
            Bucket=bucket,
            Key=key,
            ExtraArgs={"ContentType": "application/json"},
        )
        print(f"  {key} ({json_file.stat().st_size:,} bytes)")

    client.put_object(
        Bucket=bucket,
        Key=LATEST_POINTER_KEY,
        Body=timestamp.encode("utf-8"),
        ContentType="text/plain; charset=utf-8",
    )
    print(f"Updated R2 snapshot pointer: {LATEST_POINTER_KEY} -> {timestamp}")
    print(f"Snapshot uploaded: {timestamp}/")


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Upload provider GeoJSON snapshots to Cloudflare R2"
    )
    parser.add_argument(
        "--timestamp",
        type=str,
        default=None,
        help="Override timestamp prefix (default: current UTC time)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output",
        help="Directory containing JSON files (default: output/)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    if not output_dir.exists():
        print(f"Output directory not found: {output_dir}")
        raise SystemExit(1)

    upload_snapshots(output_dir, args.timestamp)


if __name__ == "__main__":
    main()
