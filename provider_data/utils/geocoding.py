"""Shared geocoding helpers."""

import os

import httpx


DEFAULT_NOMINATIM_USER_AGENT = (
    "sasecloudmap-provider-data/0.1 (https://sasecloudmap.com/; provider data refresh)"
)


def nominatim_headers() -> dict[str, str]:
    """Return a descriptive Nominatim User-Agent."""
    return {
        "User-Agent": os.getenv(
            "NOMINATIM_USER_AGENT",
            DEFAULT_NOMINATIM_USER_AGENT,
        )
    }


def nominatim_get(url: str, **kwargs) -> httpx.Response:
    """GET Nominatim with the application-identifying headers it requires."""
    headers = {**nominatim_headers(), **kwargs.pop("headers", {})}
    return httpx.get(url, headers=headers, **kwargs)
