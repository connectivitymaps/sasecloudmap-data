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
import os
from datetime import datetime, timezone
from pathlib import Path

import boto3
from dotenv import load_dotenv


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

    print(f"Uploading {len(json_files)} files to r2://{bucket}/{timestamp}/")

    for json_file in json_files:
        key = f"{timestamp}/{json_file.name}"
        client.upload_file(
            Filename=str(json_file),
            Bucket=bucket,
            Key=key,
            ExtraArgs={"ContentType": "application/json"},
        )
        print(f"  {key} ({json_file.stat().st_size:,} bytes)")

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
