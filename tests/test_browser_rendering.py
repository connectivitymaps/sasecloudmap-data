import pytest


def test_browser_rendering_json_request_uses_account_id_as_configured(monkeypatch):
    from provider_data.utils import browser_rendering

    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct-123/")
    monkeypatch.setenv("BROWSER_RENDERING_API_TOKEN", "")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token-123")
    monkeypatch.setenv(
        "BROWSER_RENDERING_JSON_MODEL", "workers-ai/@cf/moonshotai/kimi-k2.5"
    )

    captured = {}

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"success": True, "result": {"rows": []}}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return DummyResponse()

    monkeypatch.setattr(browser_rendering.httpx, "post", fake_post)

    result = browser_rendering.extract_json(
        url="https://example.com",
        prompt="Extract rows",
        response_format={"type": "json_schema", "json_schema": {"name": "rows"}},
        goto_options={"waitUntil": "networkidle0"},
    )

    assert result == {"rows": []}
    assert captured["url"] == (
        "https://api.cloudflare.com/client/v4/accounts/acct-123//browser-rendering/json"
    )
    assert captured["headers"]["Authorization"] == "Bearer token-123"
    assert captured["json"]["custom_ai"] == [
        {"model": "workers-ai/@cf/moonshotai/kimi-k2.5"}
    ]
    assert captured["json"]["gotoOptions"] == {"waitUntil": "networkidle0"}


def test_browser_rendering_markdown_request_skips_custom_ai(monkeypatch):
    from provider_data.utils import browser_rendering

    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct-123")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token-123")

    captured = {}

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"success": True, "result": "# Example"}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return DummyResponse()

    monkeypatch.setattr(browser_rendering.httpx, "post", fake_post)

    result = browser_rendering.extract_markdown(
        url="https://example.com",
        wait_for_selector={"selector": "table", "visible": True},
    )

    assert result == "# Example"
    assert "custom_ai" not in captured["json"]
    assert captured["json"]["waitForSelector"] == {
        "selector": "table",
        "visible": True,
    }


def test_forcepoint_locations_use_json_result_without_fallback(monkeypatch):
    from provider_data import forcepoint_geojson

    monkeypatch.setattr(
        forcepoint_geojson,
        "extract_forcepoint_rows_via_json",
        lambda: [
            {"country": "Germany", "city": "Berlin"},
            {"country": "Japan", "city": "Tokyo"},
        ],
    )
    monkeypatch.setattr(
        forcepoint_geojson,
        "extract_forcepoint_rows_via_markdown",
        lambda: pytest.fail("markdown fallback should not run"),
    )

    rows = forcepoint_geojson.get_forcepoint_location_rows()

    assert rows == [
        {"country": "Germany", "city": "Berlin"},
        {"country": "Japan", "city": "Tokyo"},
    ]


def test_forcepoint_locations_fall_back_to_markdown_when_json_is_empty(monkeypatch):
    from provider_data import forcepoint_geojson

    monkeypatch.setattr(
        forcepoint_geojson, "extract_forcepoint_rows_via_json", lambda: []
    )
    monkeypatch.setattr(
        forcepoint_geojson,
        "extract_forcepoint_rows_via_markdown",
        lambda: [{"country": "France", "city": "Paris"}],
    )

    rows = forcepoint_geojson.get_forcepoint_location_rows()

    assert rows == [{"country": "France", "city": "Paris"}]


def test_forcepoint_locations_fall_back_to_markdown_when_json_errors(monkeypatch):
    from provider_data import forcepoint_geojson

    def raise_timeout():
        raise RuntimeError("timed out")

    monkeypatch.setattr(
        forcepoint_geojson, "extract_forcepoint_rows_via_json", raise_timeout
    )
    monkeypatch.setattr(
        forcepoint_geojson,
        "extract_forcepoint_rows_via_markdown",
        lambda: [{"country": "France", "city": "Paris"}],
    )

    rows = forcepoint_geojson.get_forcepoint_location_rows()

    assert rows == [{"country": "France", "city": "Paris"}]


def test_forcepoint_json_parser_reads_workers_ai_wrapper(monkeypatch):
    from provider_data import forcepoint_geojson

    monkeypatch.setattr(
        forcepoint_geojson,
        "extract_json",
        lambda **_: {
            "choices": [
                {
                    "message": {
                        "content": '{"rows":[{"country":"Germany","city":"Frankfurt"}]}'
                    }
                }
            ]
        },
    )

    rows = forcepoint_geojson.extract_forcepoint_rows_via_json()

    assert rows == [{"country": "Germany", "city": "Frankfurt"}]


def test_forcepoint_markdown_parser_extracts_country_and_city_rows():
    from provider_data import forcepoint_geojson

    markdown = """
| COUNTRY | CITY | NOTES |
| --- | --- | --- |
| Germany | Berlin | EU |
| Japan | Tokyo | APAC |
"""

    rows = forcepoint_geojson.parse_forcepoint_markdown_table(markdown)

    assert rows == [
        {"country": "Germany", "city": "Berlin"},
        {"country": "Japan", "city": "Tokyo"},
    ]


def test_forcepoint_get_data_converts_nominatim_coordinates_to_lat_lon(monkeypatch):
    from provider_data import forcepoint_geojson

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"features": [{"geometry": {"coordinates": [151.2083, -33.8698]}}]}

    monkeypatch.setattr(
        forcepoint_geojson,
        "get_forcepoint_location_rows",
        lambda: [{"country": "Australia", "city": "Sydney"}],
    )
    monkeypatch.setattr(forcepoint_geojson.httpx, "get", lambda url: DummyResponse())
    monkeypatch.setattr(forcepoint_geojson.time, "sleep", lambda _: None)

    data = forcepoint_geojson.get_data()

    assert data == [{"name": "Sydney", "coordinates": [-33.8698, 151.2083]}]
