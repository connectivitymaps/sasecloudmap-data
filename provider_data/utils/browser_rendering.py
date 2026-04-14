"""Helpers for Cloudflare Browser Rendering quick actions."""

import os

import httpx
from dotenv import load_dotenv

from provider_data.utils.http_config import http_request_kwargs

DEFAULT_TIMEOUT = 60.0
DEFAULT_MODEL = "workers-ai/@cf/moonshotai/kimi-k2.5"


def extract_json(
    *,
    url: str,
    prompt: str | None = None,
    response_format: dict | None = None,
    goto_options: dict | None = None,
    wait_for_selector: dict | None = None,
    wait_for_timeout: int | None = None,
    best_attempt: bool | None = None,
    reject_resource_types: list[str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict:
    """Extract structured data from a rendered page."""
    payload = {"url": url}
    if prompt is not None:
        payload["prompt"] = prompt
    if response_format is not None:
        payload["response_format"] = response_format
    if goto_options is not None:
        payload["gotoOptions"] = goto_options
    if wait_for_selector is not None:
        payload["waitForSelector"] = wait_for_selector
    if wait_for_timeout is not None:
        payload["waitForTimeout"] = wait_for_timeout
    if best_attempt is not None:
        payload["bestAttempt"] = best_attempt
    if reject_resource_types is not None:
        payload["rejectResourceTypes"] = reject_resource_types

    model = os.getenv("BROWSER_RENDERING_JSON_MODEL", DEFAULT_MODEL)
    if model:
        payload["custom_ai"] = [{"model": model}]

    return _post_quick_action("json", payload, timeout=timeout)


def extract_markdown(
    *,
    url: str,
    goto_options: dict | None = None,
    wait_for_selector: dict | None = None,
    wait_for_timeout: int | None = None,
    best_attempt: bool | None = None,
    reject_resource_types: list[str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    """Extract markdown from a rendered page."""
    payload = {"url": url}
    if goto_options is not None:
        payload["gotoOptions"] = goto_options
    if wait_for_selector is not None:
        payload["waitForSelector"] = wait_for_selector
    if wait_for_timeout is not None:
        payload["waitForTimeout"] = wait_for_timeout
    if best_attempt is not None:
        payload["bestAttempt"] = best_attempt
    if reject_resource_types is not None:
        payload["rejectResourceTypes"] = reject_resource_types

    return _post_quick_action("markdown", payload, timeout=timeout)


def _post_quick_action(endpoint: str, payload: dict, *, timeout: float):
    load_dotenv()
    account_id = os.environ["CLOUDFLARE_ACCOUNT_ID"].strip()
    api_token = (
        os.environ.get("BROWSER_RENDERING_API_TOKEN", "").strip()
        or os.environ["CLOUDFLARE_API_TOKEN"].strip()
    )

    response = httpx.post(
        f"https://api.cloudflare.com/client/v4/accounts/{account_id}/browser-rendering/{endpoint}",
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=timeout,
        **http_request_kwargs(),
    )
    response.raise_for_status()
    body = response.json()
    if not body.get("success"):
        errors = body.get("errors") or [{"message": "Unknown Browser Rendering error"}]
        raise ValueError(errors[0]["message"])
    return body["result"]
