#!/usr/bin/env -S uv run
"""Tests for snapshot pointer resolution and uploads."""

from io import BytesIO

from botocore.exceptions import ClientError

from provider_data.utils.upload_to_r2 import LATEST_POINTER_KEY, upload_snapshots
from provider_data.utils.validate_snapshot import (
    download_snapshot,
    get_latest_snapshot_prefix,
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
            {"Contents": [{"Key": "2026-04-09/b.json"}, {"Key": "2026-04-09/readme.txt"}]},
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
