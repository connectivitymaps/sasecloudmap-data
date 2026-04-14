import importlib
import json
import sys
from pathlib import Path

import pytest


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


def test_run_provider_uses_current_python_interpreter(monkeypatch):
    from provider_data import run_all

    captured = {}

    class DummyCompletedProcess:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured.update(kwargs)
        return DummyCompletedProcess()

    monkeypatch.setattr(run_all.subprocess, "run", fake_run)

    success, error = run_all.run_provider(
        Path("provider_data/cloudflare_geojson.py"), refresh=True, dev=False, prod=False
    )

    assert success is True
    assert error is None
    assert captured["cmd"] == [
        sys.executable,
        "provider_data/cloudflare_geojson.py",
        "--refresh",
    ]


def test_run_all_uses_three_workers_for_refresh(monkeypatch):
    from provider_data import run_all

    captured = {}

    class DummyFuture:
        def result(self):
            return True, None

    future = DummyFuture()

    class DummyExecutor:
        def __init__(self, max_workers):
            captured["max_workers"] = max_workers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, *args):
            captured["submitted"] = (fn, args)
            return future

    monkeypatch.setattr(
        run_all,
        "discover_providers",
        lambda: [Path("provider_data/cloudflare_geojson.py")],
    )
    monkeypatch.setattr(run_all, "ThreadPoolExecutor", DummyExecutor)
    monkeypatch.setattr(run_all, "as_completed", lambda futures: list(futures.keys()))
    monkeypatch.setattr(run_all.sys, "argv", ["run_all.py", "--refresh"])

    with pytest.raises(SystemExit) as exc_info:
        run_all.main()

    assert exc_info.value.code == 0
    assert captured["max_workers"] == 3


def test_run_all_fails_at_end_when_fail_on_any_failure_is_enabled(monkeypatch):
    from provider_data import run_all

    class DummyFuture:
        def result(self):
            return False, ("RuntimeError: boom", "traceback")

    future = DummyFuture()

    class DummyExecutor:
        def __init__(self, max_workers):
            self.max_workers = max_workers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, *args):
            return future

    monkeypatch.setattr(
        run_all,
        "discover_providers",
        lambda: [Path("provider_data/cloudflare_geojson.py")],
    )
    monkeypatch.setattr(run_all, "ThreadPoolExecutor", DummyExecutor)
    monkeypatch.setattr(run_all, "as_completed", lambda futures: list(futures.keys()))
    monkeypatch.setattr(
        run_all.sys,
        "argv",
        ["run_all.py", "--dev", "--fail-on-any-failure"],
    )

    with pytest.raises(SystemExit) as exc_info:
        run_all.main()

    assert exc_info.value.code == 1


def test_run_all_provider_flag_accepts_declared_provider_name(monkeypatch, tmp_path):
    from provider_data import run_all

    provider_script = tmp_path / "provider_data" / "fortinet_geojson.py"
    provider_script.parent.mkdir()
    provider_script.write_text(
        'provider_name = "fortisase"\n',
        encoding="utf-8",
    )

    captured = {}

    class DummyFuture:
        def result(self):
            return True, None

    future = DummyFuture()

    class DummyExecutor:
        def __init__(self, max_workers):
            self.max_workers = max_workers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, *args):
            captured["submitted_args"] = args
            return future

    monkeypatch.setattr(run_all, "discover_providers", lambda: [provider_script])
    monkeypatch.setattr(run_all, "ThreadPoolExecutor", DummyExecutor)
    monkeypatch.setattr(run_all, "as_completed", lambda futures: list(futures.keys()))
    monkeypatch.setattr(
        run_all.sys,
        "argv",
        ["run_all.py", "--dev", "--provider", "fortisase"],
    )

    with pytest.raises(SystemExit) as exc_info:
        run_all.main()

    assert exc_info.value.code == 0
    assert captured["submitted_args"][0] == provider_script


def test_remove_failed_refresh_output_deletes_partial_output(monkeypatch, tmp_path):
    from provider_data import run_all

    provider_script = tmp_path / "provider_data" / "cloudflare_geojson.py"
    provider_script.parent.mkdir()
    provider_script.write_text(
        'provider_name = "cloudflare"\n',
        encoding="utf-8",
    )

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    output_file = output_dir / "cloudflare.json"
    output_file.write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    removed_path = run_all.remove_failed_refresh_output(provider_script)

    assert removed_path == Path("output/cloudflare.json")
    assert not output_file.exists()
