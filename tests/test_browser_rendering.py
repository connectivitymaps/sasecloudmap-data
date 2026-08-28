import pytest


def test_browser_rendering_json_request_uses_account_id(monkeypatch):
    from provider_data.utils import browser_rendering

    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct-123")
    monkeypatch.setenv("BROWSER_RENDERING_API_TOKEN", "")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token-123")
    monkeypatch.setenv("BROWSER_RENDERING_JSON_MODEL", "workers-ai/@cf/zai-org/glm-5.2")

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
        "https://api.cloudflare.com/client/v4/accounts/acct-123/browser-rendering/json"
    )
    assert captured["headers"]["Authorization"] == "Bearer token-123"
    assert captured["json"]["custom_ai"] == [
        {"model": "workers-ai/@cf/zai-org/glm-5.2"}
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


def test_forcepoint_get_data_fails_when_markdown_extraction_errors(monkeypatch):
    from provider_data import forcepoint_geojson

    def fail_markdown():
        raise RuntimeError("timed out")

    monkeypatch.setattr(
        forcepoint_geojson, "extract_forcepoint_rows_via_markdown", fail_markdown
    )

    with pytest.raises(RuntimeError, match="timed out"):
        forcepoint_geojson.get_data()


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


def test_forcepoint_markdown_parser_prefers_bold_data_center_table():
    from provider_data import forcepoint_geojson

    markdown = """
#### Data Center Locations and IP Addresses
| **COUNTRY** | **CITY** | **DATA CENTER ID** |
| --- | --- | --- |
| Germany | Frankfurt | B |

#### Local Point of Presence Locations and IP Addresses
| Country | City | Local PoP ID |
| --- | --- | --- |
| Albania | Tirana | TIAA |
"""

    assert forcepoint_geojson.parse_forcepoint_markdown_table(markdown) == [
        {"country": "Germany", "city": "Frankfurt"}
    ]


def test_forcepoint_markdown_extraction_retries_when_first_attempt_is_shell(
    monkeypatch,
):
    from provider_data import forcepoint_geojson

    responses = iter(
        [
            "Forcepoint Hub\nLoading\nCSS Error",
            """
| COUNTRY | CITY |
| --- | --- |
| Germany | Berlin |
""",
        ]
    )
    calls = []

    def fake_extract_markdown(**kwargs):
        calls.append(kwargs)
        return next(responses)

    monkeypatch.setattr(forcepoint_geojson, "extract_markdown", fake_extract_markdown)

    rows = forcepoint_geojson.extract_forcepoint_rows_via_markdown()

    assert rows == [{"country": "Germany", "city": "Berlin"}]
    assert len(calls) == 2
    assert calls[1]["wait_for_selector"] == {"selector": "table", "visible": True}


def test_forcepoint_markdown_extraction_retries_when_first_attempt_raises(
    monkeypatch,
):
    from provider_data import forcepoint_geojson

    calls = []

    def fake_extract_markdown(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError("timed out")
        return """
| COUNTRY | CITY |
| --- | --- |
| France | Paris |
"""

    monkeypatch.setattr(forcepoint_geojson, "extract_markdown", fake_extract_markdown)

    rows = forcepoint_geojson.extract_forcepoint_rows_via_markdown()

    assert rows == [{"country": "France", "city": "Paris"}]
    assert len(calls) == 2


def test_forcepoint_get_data_converts_nominatim_coordinates_to_lat_lon(monkeypatch):
    from provider_data import forcepoint_geojson

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"features": [{"geometry": {"coordinates": [151.2083, -33.8698]}}]}

    monkeypatch.setattr(
        forcepoint_geojson,
        "extract_forcepoint_rows_via_markdown",
        lambda: [{"country": "Australia", "city": "Sydney"}],
    )
    monkeypatch.setattr(
        forcepoint_geojson,
        "nominatim_get",
        lambda url, **kwargs: DummyResponse(),
    )
    monkeypatch.setattr(forcepoint_geojson.time, "sleep", lambda _: None)

    data = forcepoint_geojson.get_data()

    assert data == [{"name": "Sydney", "coordinates": [-33.8698, 151.2083]}]
