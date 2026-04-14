#!/usr/bin/env -S uv run

import argparse
import ipaddress
import os
import time

import httpx
from dotenv import load_dotenv

from provider_data.utils.http_config import http_request_kwargs


PROXY_ENDPOINT_ID = "ad4ff330-62bb-4489-b6bb-f893806ebdde"
PUBLIC_IP_ENDPOINTS = {
    4: "https://api4.ipify.org",
    6: "https://api6.ipify.org",
}


def require_env(name: str) -> str:
    """Return a required environment variable or fail clearly."""
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _normalize_endpoint(value: str) -> str:
    return value.strip().rstrip(".").lower()


def verify_proxy_endpoint_match(
    *, configured_endpoint: str, response_body: dict
) -> None:
    """Verify the Cloudflare response matches the configured proxy endpoint."""
    expected_hostname = _normalize_endpoint(configured_endpoint)
    expected_subdomain = expected_hostname.split(".", 1)[0]
    result = response_body.get("result") or {}
    hostname = result.get("hostname")
    subdomain = result.get("subdomain")

    if isinstance(hostname, str):
        if _normalize_endpoint(hostname) == expected_hostname:
            return
        raise RuntimeError(
            "Cloudflare proxy endpoint update returned a proxy endpoint that does not match PROXY_ENDPOINT."
        )

    if (
        isinstance(subdomain, str)
        and _normalize_endpoint(subdomain) == expected_subdomain
    ):
        return

    if hostname is None and subdomain is None:
        raise RuntimeError(
            "Cloudflare proxy endpoint update succeeded but the response could not verify PROXY_ENDPOINT."
        )

    raise RuntimeError(
        "Cloudflare proxy endpoint update returned a proxy endpoint that does not match PROXY_ENDPOINT."
    )


def parse_public_ip(raw_value: str, *, version: int) -> str:
    """Validate a discovered public IP address for the expected family."""
    try:
        address = ipaddress.ip_address(raw_value.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid IPv{version} address: {raw_value!r}") from exc
    if address.version != version:
        raise ValueError(
            f"Expected an IPv{version} address, received IPv{address.version}: {address}"
        )
    return str(address)


def build_patch_payload(ipv4: str, ipv6: str | None) -> dict[str, list[str]]:
    """Build the Cloudflare proxy endpoint PATCH payload."""
    payload = {"ips": [f"{parse_public_ip(ipv4, version=4)}/32"]}
    if ipv6 is not None:
        payload["ips"].append(f"{parse_public_ip(ipv6, version=6)}/128")
    return payload


def discover_public_ip(*, version: int) -> str | None:
    """Discover the current public IP address for an address family."""
    try:
        response = httpx.get(
            PUBLIC_IP_ENDPOINTS[version], timeout=10.0, **http_request_kwargs()
        )
        response.raise_for_status()
        return parse_public_ip(response.text, version=version)
    except (httpx.HTTPError, ValueError):
        if version == 6:
            print("Warning: IPv6 discovery failed; continuing with IPv4 only.")
            return None
        raise


def patch_proxy_endpoint(
    *, account_id: str, api_token: str, payload: dict[str, object]
) -> dict:
    """Patch the Cloudflare proxy endpoint allowlist."""
    response = httpx.patch(
        f"https://api.cloudflare.com/client/v4/accounts/{account_id}/gateway/proxy_endpoints/{PROXY_ENDPOINT_ID}",
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30.0,
        **http_request_kwargs(),
    )
    response.raise_for_status()
    body = response.json()
    if not body.get("success"):
        errors = body.get("errors") or []
        message = "; ".join(
            error.get("message", "Unknown Cloudflare API error") for error in errors
        )
        raise RuntimeError(
            f"Cloudflare proxy endpoint update failed: {message or 'Unknown Cloudflare API error'}"
        )
    return body


def update_proxy_endpoint(*, propagation_seconds: float) -> None:
    """Update the proxy endpoint allowlist with the current public IPs."""
    load_dotenv()
    account_id = require_env("CLOUDFLARE_ACCOUNT_ID")
    api_token = require_env("PROXY_ENDPOINT_API_TOKEN")
    proxy_endpoint = require_env("PROXY_ENDPOINT")

    print("Discovering public IP addresses...")
    ipv4 = discover_public_ip(version=4)
    ipv6 = discover_public_ip(version=6)

    print("Updating proxy endpoint IP allowlist...")
    response_body = patch_proxy_endpoint(
        account_id=account_id,
        api_token=api_token,
        payload=build_patch_payload(ipv4=ipv4, ipv6=ipv6),
    )
    verify_proxy_endpoint_match(
        configured_endpoint=proxy_endpoint, response_body=response_body
    )

    print("Proxy endpoint update complete.")
    if propagation_seconds > 0:
        print(f"Waiting {propagation_seconds:g} seconds for propagation...")
        time.sleep(propagation_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Update Cloudflare proxy endpoint IPs")
    parser.add_argument(
        "--propagation-seconds",
        type=float,
        default=0.0,
        help="Seconds to wait after a successful patch",
    )
    args = parser.parse_args()
    update_proxy_endpoint(propagation_seconds=args.propagation_seconds)


if __name__ == "__main__":
    main()
