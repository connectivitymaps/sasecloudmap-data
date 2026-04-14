#!/usr/bin/env -S uv run
"""Compare current output with the latest R2 snapshot to detect large changes.

Downloads the most recent snapshot from R2 and compares feature counts
per provider. Warns if any provider's count changed by more than a
configurable threshold (default 10%), which may indicate a broken scraper
or a changed source website.

Required environment variables:
    R2_ACCOUNT_ID        - Cloudflare account ID
    R2_ACCESS_KEY_ID     - R2 API token access key ID
    R2_SECRET_ACCESS_KEY - R2 API token secret access key
    R2_BUCKET_NAME       - R2 bucket name
"""

import argparse
import json
import os
import sys
from pathlib import Path

from botocore.exceptions import ClientError
from dotenv import load_dotenv

from provider_data.utils.provider_discovery import discover_expected_files
from provider_data.utils.upload_to_r2 import LATEST_POINTER_KEY, get_s3_client


def read_latest_snapshot_prefix(client, bucket: str) -> str | None:
    """Read the latest snapshot pointer from R2, if it exists."""
    try:
        response = client.get_object(Bucket=bucket, Key=LATEST_POINTER_KEY)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code in {"NoSuchKey", "404", "NotFound"}:
            return None
        raise

    prefix = response["Body"].read().decode("utf-8").strip()
    return prefix or None


def get_latest_snapshot_prefix(client, bucket: str) -> str | None:
    """Find the most recent snapshot prefix in R2."""
    latest_prefix = read_latest_snapshot_prefix(client, bucket)
    if latest_prefix is not None:
        return latest_prefix

    paginator = client.get_paginator("list_objects_v2")
    prefixes = []
    for page in paginator.paginate(Bucket=bucket, Delimiter="/"):
        prefixes.extend(
            prefix["Prefix"].rstrip("/") for prefix in page.get("CommonPrefixes", [])
        )
    if not prefixes:
        return None
    print(f"{LATEST_POINTER_KEY} not found in R2, falling back to prefix listing.")
    return sorted(prefixes)[-1]


def download_snapshot(client, bucket: str, prefix: str) -> dict[str, dict]:
    """Download all JSON files under a prefix. Returns {filename: parsed_json}."""
    snapshot = {}
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=f"{prefix}/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith(".json"):
                continue
            filename = key.split("/")[-1]
            body = client.get_object(Bucket=bucket, Key=key)["Body"].read()
            snapshot[filename] = json.loads(body)
    return snapshot


def count_features(geojson: dict) -> int:
    """Count features in a GeoJSON FeatureCollection."""
    return len(geojson.get("features", []))


def find_missing_expected_files(
    output_dir: Path, expected_files: set[str]
) -> list[str]:
    """Return expected files that are missing from the output directory."""
    local_files = {f.name for f in sorted(output_dir.glob("*.json"))}
    return sorted(
        expected_file
        for expected_file in expected_files
        if expected_file not in local_files
    )


def validate(
    output_dir: Path, threshold: float, expected_files: set[str] | None = None
) -> list[dict]:
    """Compare local output with latest R2 snapshot.

    Returns a list of warnings for providers that changed beyond the threshold.
    """
    client = get_s3_client()
    bucket = os.environ["R2_BUCKET_NAME"]

    prefix = get_latest_snapshot_prefix(client, bucket)
    if prefix is None:
        print("No snapshots found in R2 bucket, skipping validation.")
        return []

    print(f"Comparing against R2 snapshot: {prefix}/")

    snapshot = download_snapshot(client, bucket, prefix)
    if not snapshot:
        print(f"No JSON files found in snapshot {prefix}/, skipping validation.")
        return []

    local_files = {f.name: f for f in sorted(output_dir.glob("*.json"))}
    if not local_files:
        print("No local JSON files found in output/, skipping validation.")
        return []

    if expected_files is None:
        expected_files = discover_expected_files()
    if not expected_files:
        raise ValueError("No provider scripts discovered for snapshot validation")

    warnings = []

    # Scope validation to the providers defined in the current repo so
    # retired historical snapshot entries do not cause false failures.
    all_providers = sorted(expected_files)
    missing_files = set(find_missing_expected_files(output_dir, expected_files))

    for filename in all_providers:
        provider = filename.removesuffix(".json")

        if filename in missing_files:
            warnings.append(
                {
                    "provider": provider,
                    "old": count_features(snapshot[filename])
                    if filename in snapshot
                    else 0,
                    "new": 0,
                    "change_pct": -100.0,
                    "reason": "missing from output (scraper may have failed)",
                }
            )
            continue

        if filename not in snapshot:
            print(f"  {provider}: NEW (not in previous snapshot)")
            continue

        with open(local_files[filename]) as f:
            local_data = json.load(f)

        old_count = count_features(snapshot[filename])
        new_count = count_features(local_data)

        if old_count == 0:
            if new_count > 0:
                print(
                    f"  {provider}: {old_count} -> {new_count} (was empty, now has data)"
                )
            continue

        change_pct = ((new_count - old_count) / old_count) * 100

        if abs(change_pct) >= threshold:
            warnings.append(
                {
                    "provider": provider,
                    "old": old_count,
                    "new": new_count,
                    "change_pct": change_pct,
                    "reason": "significant change in feature count",
                }
            )
        else:
            print(f"  {provider}: {old_count} -> {new_count} ({change_pct:+.1f}%) OK")

    return warnings


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Validate provider data against previous R2 snapshot"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output",
        help="Directory containing JSON files (default: output/)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=10.0,
        help="Percentage change threshold to trigger warning (default: 10)",
    )
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="Print warnings but exit successfully",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    if not output_dir.exists():
        print(f"Output directory not found: {output_dir}")
        raise SystemExit(1)

    warnings = validate(output_dir, args.threshold)

    if warnings:
        print(f"\n{'=' * 60}")
        print(f"WARNING: {len(warnings)} provider(s) changed by >= {args.threshold}%")
        print(f"{'=' * 60}")
        for w in warnings:
            direction = "INCREASED" if w["change_pct"] > 0 else "DECREASED"
            print(
                f"  {w['provider']}: {w['old']} -> {w['new']} "
                f"({w['change_pct']:+.1f}% {direction}) — {w['reason']}"
            )
        print(f"{'=' * 60}")
        print("Review these changes before trusting the data.")
        if not args.warn_only:
            sys.exit(1)
    else:
        print("\nAll providers within expected range.")


if __name__ == "__main__":
    main()
