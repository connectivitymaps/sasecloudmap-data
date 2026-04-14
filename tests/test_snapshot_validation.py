#!/usr/bin/env -S uv run
"""Tests for snapshot pointer resolution and uploads."""

from io import BytesIO
from pathlib import Path

import pytest
import subprocess
import sys
from botocore.exceptions import ClientError

from provider_data.utils.upload_to_r2 import (
    LATEST_POINTER_KEY,
    prepare_snapshot_upload_dir,
    upload_snapshots,
)
from provider_data.utils.provider_discovery import discover_expected_files
from provider_data.utils.validate_snapshot import (
    download_snapshot,
    find_missing_expected_files,
    get_latest_snapshot_prefix,
    validate,
)


class FakePaginator:
    def __init__(self, pages):
        self.pages = pages

    def paginate(self, **kwargs):
        self.last_kwargs = kwargs
        return self.pages


class FakeS3Client:
    def __init__(self, *, latest_prefix=None, prefix_pages=None, object_pages=None):
        self.latest_prefix = latest_prefix
        self.prefix_pages = prefix_pages or []
        self.object_pages = object_pages or []
        self.uploaded_files = []
        self.put_objects = []
        self.objects = {}

    def upload_file(self, Filename, Bucket, Key, ExtraArgs):
        self.uploaded_files.append((Filename, Bucket, Key, ExtraArgs))

    def put_object(self, **kwargs):
        self.put_objects.append(kwargs)

    def get_object(self, Bucket, Key):
        if Key == LATEST_POINTER_KEY:
            if self.latest_prefix is None:
                raise ClientError(
                    {"Error": {"Code": "NoSuchKey", "Message": "missing"}},
                    "GetObject",
                )
            return {"Body": BytesIO(self.latest_prefix.encode("utf-8"))}
        return {"Body": BytesIO(self.objects[Key])}

    def get_paginator(self, operation_name):
        assert operation_name == "list_objects_v2"
        if self.object_pages:
            return FakePaginator(self.object_pages)
        return FakePaginator(self.prefix_pages)


def test_get_latest_snapshot_prefix_prefers_latest_pointer():
    client = FakeS3Client(latest_prefix="2026-04-09")

    result = get_latest_snapshot_prefix(client, "test-bucket")

    assert result == "2026-04-09"


def test_get_latest_snapshot_prefix_falls_back_to_paginated_prefix_listing():
    client = FakeS3Client(
        prefix_pages=[
            {"CommonPrefixes": [{"Prefix": "2026-04-01/"}]},
            {"CommonPrefixes": [{"Prefix": "2026-04-09/"}]},
        ]
    )

    result = get_latest_snapshot_prefix(client, "test-bucket")

    assert result == "2026-04-09"


def test_download_snapshot_reads_all_paginated_json_objects():
    client = FakeS3Client(
        latest_prefix="2026-04-09",
        object_pages=[
            {"Contents": [{"Key": "2026-04-09/a.json"}]},
            {
                "Contents": [
                    {"Key": "2026-04-09/b.json"},
                    {"Key": "2026-04-09/readme.txt"},
                ]
            },
        ],
    )
    client.objects["2026-04-09/a.json"] = b'{"features": [1]}'
    client.objects["2026-04-09/b.json"] = b'{"features": [1, 2]}'

    snapshot = download_snapshot(client, "test-bucket", "2026-04-09")

    assert snapshot == {
        "a.json": {"features": [1]},
        "b.json": {"features": [1, 2]},
    }


def test_upload_snapshots_updates_latest_pointer(monkeypatch, tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "cloudflare.json").write_text("{}", encoding="utf-8")

    client = FakeS3Client()
    monkeypatch.setenv("R2_BUCKET_NAME", "test-bucket")
    monkeypatch.setattr(
        "provider_data.utils.upload_to_r2.get_s3_client",
        lambda: client,
    )

    upload_snapshots(output_dir, "2026-04-09")

    assert client.uploaded_files[0][2] == "2026-04-09/cloudflare.json"
    assert client.put_objects == [
        {
            "Bucket": "test-bucket",
            "Key": LATEST_POINTER_KEY,
            "Body": b"2026-04-09",
            "ContentType": "text/plain; charset=utf-8",
        }
    ]


def test_prepare_snapshot_upload_dir_carries_forward_blocked_providers(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "cloudflare.json").write_text('{"features": [1]}', encoding="utf-8")
    (output_dir / "zscaler.json").write_text('{"features": [2]}', encoding="utf-8")

    staging_dir = tmp_path / "staging"
    staged_current, carried_forward = prepare_snapshot_upload_dir(
        output_dir,
        staging_dir,
        {"cloudflare.json"},
        expected_files={"cloudflare.json", "zscaler.json", "forcepoint.json"},
        previous_snapshot={
            "zscaler.json": {"features": ["old-zscaler"]},
            "forcepoint.json": {"features": ["old-forcepoint"]},
        },
    )

    assert staged_current == ["cloudflare.json"]
    assert carried_forward == ["forcepoint.json", "zscaler.json"]
    assert (staging_dir / "cloudflare.json").read_text(encoding="utf-8") == (
        '{"features": [1]}'
    )
    assert (staging_dir / "zscaler.json").read_text(encoding="utf-8") == (
        '{"features": ["old-zscaler"]}'
    )
    assert (staging_dir / "forcepoint.json").read_text(encoding="utf-8") == (
        '{"features": ["old-forcepoint"]}'
    )


def test_validate_ignores_retired_providers_present_only_in_snapshot(
    monkeypatch, tmp_path
):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "cloudflare.json").write_text(
        '{"features": [1, 2]}', encoding="utf-8"
    )

    client = FakeS3Client(
        latest_prefix="2026-04-09",
        object_pages=[
            {
                "Contents": [
                    {"Key": "2026-04-09/cloudflare.json"},
                    {"Key": "2026-04-09/akamai.json"},
                ]
            }
        ],
    )
    client.objects["2026-04-09/cloudflare.json"] = b'{"features": [1, 2]}'
    client.objects["2026-04-09/akamai.json"] = b'{"features": [1, 2, 3]}'

    monkeypatch.setenv("R2_BUCKET_NAME", "test-bucket")
    monkeypatch.setattr(
        "provider_data.utils.validate_snapshot.get_s3_client",
        lambda: client,
    )

    warnings = validate(
        output_dir,
        threshold=10.0,
        expected_files={"cloudflare.json"},
    )

    assert warnings == []


def test_validate_warns_when_active_provider_is_missing_from_output(
    monkeypatch, tmp_path
):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "cloudflare.json").write_text('{"features": [1]}', encoding="utf-8")

    client = FakeS3Client(
        latest_prefix="2026-04-09",
        object_pages=[
            {
                "Contents": [
                    {"Key": "2026-04-09/cloudflare.json"},
                    {"Key": "2026-04-09/forcepoint.json"},
                ]
            }
        ],
    )
    client.objects["2026-04-09/cloudflare.json"] = b'{"features": [1]}'
    client.objects["2026-04-09/forcepoint.json"] = b'{"features": [1, 2, 3]}'

    monkeypatch.setenv("R2_BUCKET_NAME", "test-bucket")
    monkeypatch.setattr(
        "provider_data.utils.validate_snapshot.get_s3_client",
        lambda: client,
    )

    warnings = validate(
        output_dir,
        threshold=10.0,
        expected_files={"cloudflare.json", "forcepoint.json"},
    )

    assert warnings == [
        {
            "provider": "forcepoint",
            "old": 3,
            "new": 0,
            "change_pct": -100.0,
            "reason": "missing from output (scraper may have failed)",
        }
    ]


def test_discover_expected_files_supports_assign_and_annotated_assign(tmp_path):
    provider_dir = tmp_path / "provider_data"
    provider_dir.mkdir()
    (provider_dir / "alpha_geojson.py").write_text(
        'provider_name = "alpha"\n',
        encoding="utf-8",
    )
    (provider_dir / "beta.py").write_text(
        'provider_name: str = "beta"\n',
        encoding="utf-8",
    )
    (provider_dir / "run_all.py").write_text("", encoding="utf-8")
    (provider_dir / "__init__.py").write_text("", encoding="utf-8")

    assert discover_expected_files(provider_dir) == {"alpha.json", "beta.json"}


def test_discover_expected_files_raises_on_invalid_provider_script(tmp_path):
    provider_dir = tmp_path / "provider_data"
    provider_dir.mkdir()
    (provider_dir / "alpha_geojson.py").write_text(
        "provider_name = compute_name()\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unable to discover provider_name"):
        discover_expected_files(provider_dir)


def test_find_missing_expected_files_reports_only_active_missing_outputs(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "cloudflare.json").write_text("{}", encoding="utf-8")

    assert find_missing_expected_files(
        output_dir,
        {"cloudflare.json", "forcepoint.json"},
    ) == ["forcepoint.json"]


def test_validate_fails_closed_when_expected_files_cannot_be_discovered(
    monkeypatch, tmp_path
):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "cloudflare.json").write_text('{"features": [1]}', encoding="utf-8")

    client = FakeS3Client(
        latest_prefix="2026-04-09",
        object_pages=[{"Contents": [{"Key": "2026-04-09/cloudflare.json"}]}],
    )
    client.objects["2026-04-09/cloudflare.json"] = b'{"features": [1]}'

    monkeypatch.setenv("R2_BUCKET_NAME", "test-bucket")
    monkeypatch.setattr(
        "provider_data.utils.validate_snapshot.get_s3_client",
        lambda: client,
    )
    monkeypatch.setattr(
        "provider_data.utils.validate_snapshot.discover_expected_files",
        lambda provider_dir=None: set(),
    )

    with pytest.raises(ValueError, match="No provider scripts discovered"):
        validate(output_dir, threshold=10.0)


def test_validate_main_warn_only_does_not_exit_nonzero_on_warnings(
    monkeypatch, tmp_path
):
    from provider_data.utils import validate_snapshot

    output_dir = tmp_path / "output"
    output_dir.mkdir()

    monkeypatch.setattr(validate_snapshot, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        validate_snapshot,
        "validate",
        lambda output_dir, threshold: [
            {
                "provider": "forcepoint",
                "old": 3,
                "new": 0,
                "change_pct": -100.0,
                "reason": "missing from output (scraper may have failed)",
            }
        ],
    )
    monkeypatch.setattr(
        validate_snapshot.sys,
        "argv",
        [
            "validate_snapshot.py",
            "--output-dir",
            str(output_dir),
            "--warn-only",
        ],
    )

    validate_snapshot.main()


def test_validate_snapshot_script_executes_directly_without_http_shadowing():
    result = subprocess.run(
        [
            sys.executable,
            "provider_data/utils/validate_snapshot.py",
            "--help",
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent,
    )

    assert result.returncode == 0
    assert "Validate provider data against previous R2 snapshot" in result.stdout
