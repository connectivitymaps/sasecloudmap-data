import json

import pytest


def test_write_geojson_output_rejects_empty_features_without_overwriting_existing(
    tmp_path,
):
    from provider_data.utils.output import write_geojson_output

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    output_file = output_dir / "forcepoint.json"
    original = {"type": "FeatureCollection", "features": [{"type": "Feature"}]}
    output_file.write_text(json.dumps(original), encoding="utf-8")

    with pytest.raises(ValueError, match="forcepoint produced 0 features"):
        write_geojson_output(
            "forcepoint",
            {"type": "FeatureCollection", "features": []},
            output_dir=output_dir,
        )

    assert json.loads(output_file.read_text(encoding="utf-8")) == original


def test_write_and_post_rejects_empty_dev_payload_before_http_post(
    monkeypatch,
    tmp_path,
):
    from provider_data.utils.post_data import write_and_post

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "forcepoint.json").write_text(
        json.dumps({"type": "FeatureCollection", "features": []}),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTH", "test-auth")
    monkeypatch.setenv("BMS", "test-bms")
    monkeypatch.setenv("DEV_HOSTNAME", "https://dev.example.test/add/")

    posts = []
    monkeypatch.setattr(
        "provider_data.utils.post_data.httpx.post",
        lambda *args, **kwargs: posts.append((args, kwargs)),
    )

    with pytest.raises(ValueError, match="forcepoint has 0 features"):
        write_and_post(
            "forcepoint",
            "Forcepoint",
            ["sase"],
            update_dev=True,
        )

    assert posts == []
