#!/usr/bin/env -S uv run
import argparse
import json
import re
import sys
import time

import httpx
from provider_data.utils.base import convert_to_geojson as base_convert_to_geojson
from provider_data.utils.browser_rendering import extract_json, extract_markdown
from provider_data.utils.http_config import http_request_kwargs
from provider_data.utils.post_data import write_and_post
from provider_data.utils.skeleton import geojson_skeleton

FORCEPOINT_URL = "https://support.forcepoint.com/s/article/Cloud-service-data-center-IP-addresses-port-numbers"


def get_forcepoint_location_rows():
    try:
        rows = extract_forcepoint_rows_via_json()
        if rows:
            return rows
    except Exception as exc:
        print(
            f"Browser Rendering JSON extraction failed, falling back to markdown: {exc}"
        )
    return extract_forcepoint_rows_via_markdown()


def extract_forcepoint_rows_via_json():
    result = extract_json(
        url=FORCEPOINT_URL,
        prompt=(
            "Extract only the Forcepoint cloud service data center table rows. "
            "Return country and city fields for each location. Ignore IP addresses, ports, "
            "headers, notes, and unrelated tables."
        ),
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "forcepoint_locations",
                "schema": {
                    "type": "object",
                    "properties": {
                        "rows": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "country": {"type": "string"},
                                    "city": {"type": "string"},
                                },
                                "required": ["country", "city"],
                                "additionalProperties": False,
                            },
                        }
                    },
                    "required": ["rows"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        goto_options={"waitUntil": "load", "timeout": 45000},
        wait_for_selector={"selector": "table", "visible": True},
        wait_for_timeout=5000,
        best_attempt=True,
    )
    return normalize_forcepoint_rows(_extract_rows_from_json_result(result))


def extract_forcepoint_rows_via_markdown():
    errors = []
    attempts = [
        {
            "goto_options": {"waitUntil": "load", "timeout": 45000},
            "wait_for_timeout": 5000,
            "best_attempt": True,
        },
        {
            "goto_options": {"waitUntil": "networkidle", "timeout": 60000},
            "wait_for_selector": {"selector": "table", "visible": True},
            "wait_for_timeout": 10000,
            "best_attempt": True,
        },
    ]

    for attempt in attempts:
        try:
            markdown = extract_markdown(url=FORCEPOINT_URL, **attempt)
            rows = parse_forcepoint_markdown_table(markdown)
            if rows:
                return rows
        except Exception as exc:
            errors.append(str(exc))

    if errors:
        raise ValueError(
            "Could not find Forcepoint data center locations table: "
            + "; ".join(errors)
        )
    raise ValueError("Could not find Forcepoint data center locations table")


def parse_forcepoint_markdown_table(markdown: str) -> list[dict[str, str]]:
    rows = []
    in_target_table = False

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            if in_target_table and rows:
                break
            continue

        cells = [cell.strip() for cell in line.strip("|").split("|")]
        normalized = [cell.upper() for cell in cells]
        if "COUNTRY" in normalized and "CITY" in normalized:
            country_index = normalized.index("COUNTRY")
            city_index = normalized.index("CITY")
            in_target_table = True
            continue

        if not in_target_table or _is_markdown_separator_row(cells):
            continue

        if len(cells) <= max(country_index, city_index):
            continue

        country = cells[country_index]
        city = cells[city_index]
        if country and city:
            rows.append({"country": country, "city": city})

    return normalize_forcepoint_rows(rows)


def normalize_forcepoint_rows(rows: list[dict]) -> list[dict[str, str]]:
    normalized = []
    for row in rows:
        country = str(row.get("country", "")).strip()
        city = str(row.get("city", "")).strip()
        if country and city:
            normalized.append({"country": country, "city": city})
    return normalized


def _extract_rows_from_json_result(result: dict) -> list[dict]:
    rows = result.get("rows")
    if isinstance(rows, list):
        return rows

    choices = result.get("choices") or []
    if not choices:
        return []

    content = choices[0].get("message", {}).get("content")
    if not isinstance(content, str):
        return []

    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(parsed, dict):
        rows = parsed.get("rows")
        if isinstance(rows, list):
            return rows
    return []


def _is_markdown_separator_row(cells: list[str]) -> bool:
    return all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells if cell)


def get_data():
    data = get_forcepoint_location_rows()

    locations = []
    for row in data:
        city = row["city"]
        country = row["country"]
        try:
            geolocation = httpx.get(
                f"https://nominatim.openstreetmap.org/search?format=geojson&polygon=1&addressdetails=1&limit=1&accept-language=en&q={city},{country}",
                **http_request_kwargs(),
            )
            geolocation.raise_for_status()
            resp = geolocation.json()
            longitude, latitude = resp["features"][0]["geometry"]["coordinates"]
            geometry = {
                "name": city,
                "coordinates": [latitude, longitude],
            }
            locations.append(geometry)
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            print(f"HTTP error for location {city}, {country}: {e}")
        except (KeyError, IndexError, ValueError) as e:
            print(f"Failed to parse location {city}, {country}: {e}")
        finally:
            time.sleep(1)  # Nominatim rate limit: 1 request/second

    return locations


def convert_to_geojson(data):
    """Convert passed data to proper GeoJSON."""
    return base_convert_to_geojson(data)


if __name__ == "__main__":
    provider_name = "forcepoint"
    friendly_name = "Forcepoint"
    app_type = ["sase"]

    parser = argparse.ArgumentParser(
        description="Update dev, prod or both environments."
    )
    parser.add_argument("--refresh", action="store_true", help="refresh from source")
    parser.add_argument("--dev", action="store_true", help="Update dev environment")
    parser.add_argument("--prod", action="store_true", help="Update prod environment")
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)
    args = parser.parse_args()

    if args.refresh:
        output = get_data()
        geojson = convert_to_geojson(output)
        geojson_data = geojson_skeleton(geojson)

        with open(f"output/{provider_name}.json", "w", encoding="utf-8") as f:
            json.dump(geojson_data, f, ensure_ascii=False)

    write_and_post(
        provider_name,
        friendly_name,
        app_type,
        update_dev=args.dev,
        update_prod=args.prod,
    )
