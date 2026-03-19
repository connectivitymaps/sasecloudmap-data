import importlib
import json
import sys


class DummyResponse:
    def __init__(self, text="ok", json_data=None):
        self.text = text
        self._json_data = {} if json_data is None else json_data

    def json(self):
        return self._json_data


def write_output_file(tmp_path, provider_name, payload=None):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    with open(output_dir / f"{provider_name}.json", "w", encoding="utf-8") as file:
        json.dump(
            {"type": "FeatureCollection", "features": []}
            if payload is None
            else payload,
            file,
        )


def test_write_and_post_sets_timeout_for_dev_update(monkeypatch, tmp_path):
    from provider_data.utils import post_data

    write_output_file(tmp_path, "provider")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTH", "auth-token")
    monkeypatch.setenv("BMS", "bms-token")
    monkeypatch.setenv("DEV_HOSTNAME", "https://dev.example.com/add/")
    monkeypatch.setenv("PROD_HOSTNAME", "https://prod.example.com/add/")
    monkeypatch.setattr(post_data, "load_dotenv", lambda: None)

    calls = []

    def fake_post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return DummyResponse()

    monkeypatch.setattr(post_data.httpx, "post", fake_post)

    post_data.write_and_post(
        "provider",
        "Provider",
        ["sase"],
        update_dev=True,
    )

    assert len(calls) == 1
    assert calls[0].get("timeout") is not None


def test_write_and_post_sets_timeout_for_prod_sync_requests(monkeypatch, tmp_path):
    from provider_data.utils import post_data

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTH", "auth-token")
    monkeypatch.setenv("BMS", "bms-token")
    monkeypatch.setenv("DEV_HOSTNAME", "https://dev.example.com/add/")
    monkeypatch.setenv("PROD_HOSTNAME", "https://prod.example.com/add/")
    monkeypatch.setattr(post_data, "load_dotenv", lambda: None)

    get_calls = []
    post_calls = []

    def fake_get(url, **kwargs):
        get_calls.append({"url": url, **kwargs})
        return DummyResponse(json_data={"type": "FeatureCollection", "features": []})

    def fake_post(url, **kwargs):
        post_calls.append({"url": url, **kwargs})
        return DummyResponse()

    monkeypatch.setattr(post_data.httpx, "get", fake_get)
    monkeypatch.setattr(post_data.httpx, "post", fake_post)

    post_data.write_and_post(
        "provider",
        "Provider",
        ["sase"],
        update_prod=True,
    )

    assert len(get_calls) == 1
    assert get_calls[0].get("timeout") is not None
    assert len(post_calls) == 1
    assert post_calls[0].get("timeout") is not None


def test_generate_sitemap_import_has_no_dotenv_side_effect(monkeypatch):
    import dotenv

    calls = []

    def fake_load_dotenv():
        calls.append(True)

    monkeypatch.setattr(dotenv, "load_dotenv", fake_load_dotenv)
    sys.modules.pop("provider_data.utils.generate_sitemap", None)

    importlib.import_module("provider_data.utils.generate_sitemap")

    assert calls == []
