import json
from pathlib import Path

import pytest


WORKTREE_ROOT = Path(__file__).resolve().parent.parent


def _read_workflow(relative_path: str) -> str:
    return (WORKTREE_ROOT / relative_path).read_text(encoding="utf-8")


def _job_block(workflow_text: str, job_name: str) -> str:
    lines = workflow_text.splitlines()
    start = lines.index(f"  {job_name}:")
    end = len(lines)

    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.startswith("  ") and not line.startswith("    ") and line.endswith(":"):
            end = index
            break

    return "\n".join(lines[start:end])


def test_build_provider_status_marks_snapshot_warning_as_ineligible():
    from provider_data.utils.workflow_status import build_provider_status

    status = build_provider_status(
        provider_name="forcepoint",
        script="forcepoint_geojson",
        output_file="forcepoint.json",
        refresh_outcome="success",
        output_exists=True,
        snapshot_outcome="failure",
        deploy_outcome="skipped",
    )

    assert status["eligible_for_snapshot"] is False
    assert status["reasons"] == ["snapshot_warning"]


def test_finalize_dev_update_uploads_carried_forward_snapshot_without_fresh_files(
    monkeypatch, tmp_path
):
    from provider_data.utils import finalize_dev_update

    artifacts_dir = tmp_path / "artifacts"
    status_dir = artifacts_dir / "provider-status-cloudflare"
    status_dir.mkdir(parents=True)
    (status_dir / "cloudflare.json").write_text(
        json.dumps(
            {
                "provider_name": "cloudflare",
                "script": "cloudflare_geojson",
                "output_file": "cloudflare.json",
                "refresh_outcome": "success",
                "output_exists": True,
                "snapshot_outcome": "failure",
                "deploy_outcome": "skipped",
                "eligible_for_snapshot": False,
                "reasons": ["snapshot_warning"],
            }
        ),
        encoding="utf-8",
    )

    output_dir = tmp_path / "output"
    output_dir.mkdir()

    monkeypatch.setenv("R2_BUCKET_NAME", "test-bucket")
    monkeypatch.setattr(finalize_dev_update, "load_dotenv", lambda: None)
    monkeypatch.setattr(finalize_dev_update, "get_s3_client", lambda: object())
    monkeypatch.setattr(
        finalize_dev_update,
        "get_latest_snapshot_prefix",
        lambda client, bucket: "2026-04-09",
    )
    monkeypatch.setattr(
        finalize_dev_update,
        "download_snapshot",
        lambda client, bucket, prefix: {"cloudflare.json": {"features": ["old"]}},
    )

    captured = {}

    def fake_upload_snapshots(staging_dir, timestamp=None):
        captured["timestamp"] = timestamp
        captured["files"] = sorted(path.name for path in staging_dir.glob("*.json"))
        captured["payload"] = (staging_dir / "cloudflare.json").read_text(
            encoding="utf-8"
        )

    monkeypatch.setattr(finalize_dev_update, "upload_snapshots", fake_upload_snapshots)

    result = finalize_dev_update.finalize_dev_update(
        expected_records=[
            {
                "script": "cloudflare_geojson",
                "provider_name": "cloudflare",
                "output_file": "cloudflare.json",
            }
        ],
        artifacts_dir=artifacts_dir,
        output_dir=output_dir,
    )

    assert result["has_deployed"] is False
    assert result["staged_current"] == []
    assert result["carried_forward"] == ["cloudflare.json"]
    assert captured["files"] == ["cloudflare.json"]
    assert captured["payload"] == '{"features": ["old"]}'


def test_finalize_dev_update_cleans_up_temporary_staging_directory(
    monkeypatch, tmp_path
):
    from provider_data.utils import finalize_dev_update

    artifacts_dir = tmp_path / "artifacts"
    status_dir = artifacts_dir / "provider-status-cloudflare"
    status_dir.mkdir(parents=True)
    (status_dir / "cloudflare.json").write_text(
        json.dumps(
            {
                "provider_name": "cloudflare",
                "script": "cloudflare_geojson",
                "output_file": "cloudflare.json",
                "refresh_outcome": "success",
                "output_exists": True,
                "snapshot_outcome": "success",
                "deploy_outcome": "success",
                "eligible_for_snapshot": True,
                "reasons": [],
            }
        ),
        encoding="utf-8",
    )

    output_artifact_dir = artifacts_dir / "provider-output-cloudflare"
    output_artifact_dir.mkdir(parents=True)
    (output_artifact_dir / "cloudflare.json").write_text("{}", encoding="utf-8")

    monkeypatch.setenv("R2_BUCKET_NAME", "test-bucket")
    monkeypatch.setattr(finalize_dev_update, "load_dotenv", lambda: None)
    monkeypatch.setattr(finalize_dev_update, "get_s3_client", lambda: object())
    monkeypatch.setattr(
        finalize_dev_update, "get_latest_snapshot_prefix", lambda client, bucket: None
    )

    state = {"cleaned": False}

    class FakeTemporaryDirectory:
        def __init__(self, *, prefix):
            self.path = tmp_path / "temp-staging"
            self.path.mkdir()

        def __enter__(self):
            return str(self.path)

        def __exit__(self, exc_type, exc, tb):
            state["cleaned"] = True

    monkeypatch.setattr(
        finalize_dev_update.tempfile, "TemporaryDirectory", FakeTemporaryDirectory
    )
    monkeypatch.setattr(
        finalize_dev_update,
        "upload_snapshots",
        lambda staging_dir, timestamp=None: None,
    )

    finalize_dev_update.finalize_dev_update(
        expected_records=[
            {
                "script": "cloudflare_geojson",
                "provider_name": "cloudflare",
                "output_file": "cloudflare.json",
            }
        ],
        artifacts_dir=artifacts_dir,
        output_dir=tmp_path / "output",
    )

    assert state["cleaned"] is True


def test_validate_provider_snapshot_wrapper_filters_to_single_expected_file(
    monkeypatch, tmp_path
):
    from provider_data.utils import validate_provider_snapshot

    captured = {}

    monkeypatch.setattr(validate_provider_snapshot, "load_dotenv", lambda: None)

    def fake_validate(output_dir, threshold, expected_files):
        captured["output_dir"] = output_dir
        captured["threshold"] = threshold
        captured["expected_files"] = expected_files
        return []

    monkeypatch.setattr(validate_provider_snapshot, "validate", fake_validate)
    monkeypatch.setattr(
        "sys.argv",
        [
            "validate_provider_snapshot.py",
            "--expected-file",
            "cloudflare.json",
            "--output-dir",
            str(tmp_path),
            "--threshold",
            "12.5",
        ],
    )

    validate_provider_snapshot.main()

    assert captured["output_dir"] == tmp_path
    assert captured["threshold"] == 12.5
    assert captured["expected_files"] == {"cloudflare.json"}


def test_validate_provider_snapshot_wrapper_exits_nonzero_on_warning(monkeypatch):
    from provider_data.utils import validate_provider_snapshot

    monkeypatch.setattr(validate_provider_snapshot, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        validate_provider_snapshot,
        "validate",
        lambda output_dir, threshold, expected_files: [{"provider": "cloudflare"}],
    )
    monkeypatch.setattr(
        "sys.argv",
        ["validate_provider_snapshot.py", "--expected-file", "cloudflare.json"],
    )

    with pytest.raises(SystemExit, match="1"):
        validate_provider_snapshot.main()


@pytest.mark.parametrize(
    ("workflow_path", "provider_step_name"),
    [
        (
            ".github/workflows/update_dev_unified.yaml",
            'name: "Refresh ${{ matrix.provider.provider_name }}"',
        ),
        (
            ".github/workflows/update_main.yaml",
            'name: "Update ${{ matrix.provider.provider_name }}"',
        ),
    ],
)
def test_update_providers_workflow_serializes_proxy_setup(
    workflow_path, provider_step_name
):
    job_block = _job_block(_read_workflow(workflow_path), "update-providers")

    assert 'group: "shared-proxy-endpoint"' in job_block
    assert "max-parallel: 1" in job_block
    assert 'name: "Install the project"' in job_block
    assert 'name: "Authorize runner IP for shared proxy endpoint"' in job_block
    assert 'name: "Export HTTPS proxy environment"' in job_block
    assert provider_step_name in job_block
    assert (
        "uv run python -m provider_data.utils.update_proxy_endpoint"
        " --propagation-seconds 15" in job_block
    )
    assert "source .env" in job_block
    assert (
        'echo "HTTPS_PROXY=https://${PROXY_ENDPOINT}:443" >> "$GITHUB_ENV"' in job_block
    )

    install_index = job_block.index('name: "Install the project"')
    authorize_index = job_block.index(
        'name: "Authorize runner IP for shared proxy endpoint"'
    )
    export_index = job_block.index('name: "Export HTTPS proxy environment"')
    provider_step_index = job_block.index(provider_step_name, export_index + 1)

    assert install_index < authorize_index < export_index < provider_step_index
