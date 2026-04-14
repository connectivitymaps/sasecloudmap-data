import pytest


def test_build_patch_payload_includes_ipv4_and_ipv6_cidrs():
    from provider_data.utils.update_proxy_endpoint import build_patch_payload

    payload = build_patch_payload("203.0.113.10", "2001:db8::10")

    assert payload == {
        "ips": ["203.0.113.10/32", "2001:db8::10/128"],
    }


def test_build_patch_payload_supports_ipv4_only():
    from provider_data.utils.update_proxy_endpoint import build_patch_payload

    payload = build_patch_payload("203.0.113.10", None)

    assert payload == {"ips": ["203.0.113.10/32"]}


def test_parse_public_ip_rejects_wrong_address_family():
    from provider_data.utils.update_proxy_endpoint import parse_public_ip

    with pytest.raises(ValueError, match="IPv4"):
        parse_public_ip("2001:db8::10", version=4)


def test_patch_proxy_endpoint_raises_when_cloudflare_reports_failure(monkeypatch):
    from provider_data.utils import update_proxy_endpoint

    captured = {}

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "success": False,
                "errors": [{"message": "request rejected"}],
            }

    def fake_patch(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return DummyResponse()

    monkeypatch.setattr(update_proxy_endpoint.httpx, "patch", fake_patch)
    monkeypatch.setattr(
        update_proxy_endpoint, "http_request_kwargs", lambda: {"verify": object()}
    )

    with pytest.raises(RuntimeError, match="request rejected"):
        update_proxy_endpoint.patch_proxy_endpoint(
            account_id="acct-123",
            api_token="token-123",
            payload={"ips": ["203.0.113.10/32"]},
        )

    assert captured["url"].endswith(
        "/accounts/acct-123/gateway/proxy_endpoints/ad4ff330-62bb-4489-b6bb-f893806ebdde"
    )
    assert captured["headers"] == {
        "Authorization": "Bearer token-123",
        "Content-Type": "application/json",
    }
    assert captured["json"] == {"ips": ["203.0.113.10/32"]}


def test_discover_public_ip_treats_invalid_ipv6_response_as_best_effort(
    monkeypatch, capsys
):
    from provider_data.utils import update_proxy_endpoint

    class DummyResponse:
        text = "not-an-ip"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(
        update_proxy_endpoint.httpx, "get", lambda *args, **kwargs: DummyResponse()
    )
    monkeypatch.setattr(update_proxy_endpoint, "http_request_kwargs", lambda: {})

    assert update_proxy_endpoint.discover_public_ip(version=6) is None
    assert "IPv6 discovery failed" in capsys.readouterr().out


def test_update_proxy_endpoint_continues_without_ipv6_and_sleeps(monkeypatch):
    from provider_data.utils import update_proxy_endpoint

    monkeypatch.setattr(update_proxy_endpoint, "load_dotenv", lambda: None)
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct-123")
    monkeypatch.setenv("PROXY_ENDPOINT_API_TOKEN", "token-123")
    monkeypatch.setenv("PROXY_ENDPOINT", "proxy.example.com")

    version_calls = []
    captured = {}
    sleep_calls = []

    def fake_discover_public_ip(*, version):
        version_calls.append(version)
        if version == 4:
            return "203.0.113.10"
        return None

    def fake_patch_proxy_endpoint(*, account_id, api_token, payload):
        captured["account_id"] = account_id
        captured["api_token"] = api_token
        captured["payload"] = payload
        return {"success": True, "result": {"hostname": "proxy.example.com"}}

    monkeypatch.setattr(
        update_proxy_endpoint, "discover_public_ip", fake_discover_public_ip
    )
    monkeypatch.setattr(
        update_proxy_endpoint, "patch_proxy_endpoint", fake_patch_proxy_endpoint
    )
    monkeypatch.setattr(update_proxy_endpoint.time, "sleep", sleep_calls.append)

    update_proxy_endpoint.update_proxy_endpoint(propagation_seconds=1.5)

    assert version_calls == [4, 6]
    assert captured == {
        "account_id": "acct-123",
        "api_token": "token-123",
        "payload": {"ips": ["203.0.113.10/32"]},
    }
    assert sleep_calls == [1.5]


def test_update_proxy_endpoint_raises_on_proxy_endpoint_mismatch(monkeypatch):
    from provider_data.utils import update_proxy_endpoint

    monkeypatch.setattr(update_proxy_endpoint, "load_dotenv", lambda: None)
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct-123")
    monkeypatch.setenv("PROXY_ENDPOINT_API_TOKEN", "token-123")
    monkeypatch.setenv("PROXY_ENDPOINT", "proxy.example.com")

    monkeypatch.setattr(
        update_proxy_endpoint,
        "discover_public_ip",
        lambda *, version: "203.0.113.10" if version == 4 else None,
    )
    monkeypatch.setattr(
        update_proxy_endpoint,
        "patch_proxy_endpoint",
        lambda **kwargs: {"success": True, "result": {"hostname": "other.example.com"}},
    )
    monkeypatch.setattr(update_proxy_endpoint.time, "sleep", lambda _: None)

    with pytest.raises(RuntimeError, match="PROXY_ENDPOINT"):
        update_proxy_endpoint.update_proxy_endpoint(propagation_seconds=0)


def test_verify_proxy_endpoint_match_requires_hostname_match_before_subdomain_fallback():
    from provider_data.utils.update_proxy_endpoint import verify_proxy_endpoint_match

    with pytest.raises(RuntimeError, match="PROXY_ENDPOINT"):
        verify_proxy_endpoint_match(
            configured_endpoint="proxy.example.com",
            response_body={
                "result": {
                    "hostname": "other.example.com",
                    "subdomain": "proxy",
                }
            },
        )


def test_update_proxy_endpoint_warns_when_ipv6_discovery_fails_and_continues(
    monkeypatch, capsys
):
    from provider_data.utils import update_proxy_endpoint

    monkeypatch.setattr(update_proxy_endpoint, "load_dotenv", lambda: None)
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct-123")
    monkeypatch.setenv("PROXY_ENDPOINT_API_TOKEN", "token-123")
    monkeypatch.setenv("PROXY_ENDPOINT", "proxy.example.com")

    class IPv4Response:
        text = "203.0.113.10"

        def raise_for_status(self):
            return None

    def fake_get(url, **kwargs):
        if url == update_proxy_endpoint.PUBLIC_IP_ENDPOINTS[4]:
            return IPv4Response()
        raise update_proxy_endpoint.httpx.ConnectError("unreachable")

    captured = {}

    monkeypatch.setattr(update_proxy_endpoint.httpx, "get", fake_get)
    monkeypatch.setattr(update_proxy_endpoint, "http_request_kwargs", lambda: {})
    monkeypatch.setattr(
        update_proxy_endpoint,
        "patch_proxy_endpoint",
        lambda **kwargs: (
            captured.update(kwargs)
            or {"success": True, "result": {"hostname": "proxy.example.com"}}
        ),
    )
    monkeypatch.setattr(update_proxy_endpoint.time, "sleep", lambda _: None)

    update_proxy_endpoint.update_proxy_endpoint(propagation_seconds=0)

    assert captured["payload"] == {"ips": ["203.0.113.10/32"]}
    assert "IPv6 discovery failed" in capsys.readouterr().out
