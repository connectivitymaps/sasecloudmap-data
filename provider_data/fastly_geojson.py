#!/usr/bin/env -S uv run
import argparse
import re
import sys
import time
from typing import TypedDict

import httpx
from bs4 import BeautifulSoup
from utils.base import convert_to_geojson
from utils.geocoding import nominatim_get
from utils.http_config import http_request_kwargs
from utils.output import write_geojson_output
from utils.post_data import write_and_post
from utils.skeleton import geojson_skeleton

FASTLY_POP_URL = "https://www.fastly.com/documentation/guides/getting-started/concepts/using-fastlys-global-pop-network/"


class PopRow(TypedDict):
    location: str
    pop_code: str
    coordinates: tuple[float, float]


def parse_approx_location(text: str) -> tuple[float, float] | None:
    """Parse latitude and longitude from an approximate location string.

    Accepts comma-separated decimal coordinates such as "-34.9285, 138.6007".
    Returns (latitude, longitude) or None if parsing fails.
    """
    text = text.strip()
    if not text:
        return None

    match = re.match(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$", text)
    if not match:
        return None

    try:
        latitude = float(match.group(1))
        longitude = float(match.group(2))
    except ValueError:
        return None

    return latitude, longitude


def extract_coordinates(cell) -> tuple[float, float] | None:
    """Parse coordinates from the approximate location cell text."""
    text = cell.get_text(" ", strip=True)
    return parse_approx_location(text)


def extract_location_rows(html: str) -> list[PopRow]:
    """Parse Fastly POP rows from the documentation HTML.

    Returns a list of dicts with location name, POP code, and (lat, lon).
    """
    soup = BeautifulSoup(html, "html.parser")
    heading = soup.find(id="complete-list-of-pops")
    if heading is None:
        raise ValueError("Could not find Fastly 'Complete list of POPs' section")

    table = heading.find_next("table")
    if table is None:
        raise ValueError("Could not find Fastly POP table")

    rows = []
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue

        location = cells[0].get_text(" ", strip=True)
        pop_code = cells[1].get_text(" ", strip=True)
        coordinates = extract_coordinates(cells[2])

        if not location or not pop_code or coordinates is None:
            continue

        rows.append(
            {
                "location": location,
                "pop_code": pop_code,
                "coordinates": coordinates,
            }
        )
    return rows


def country_code_from_coordinates(latitude: float, longitude: float) -> str | None:
    """Reverse-geocode coordinates with Nominatim and return the ISO country code."""
    url = (
        "https://nominatim.openstreetmap.org/reverse?"
        f"format=jsonv2&lat={latitude}&lon={longitude}&zoom=3&addressdetails=1"
    )
    try:
        req = nominatim_get(url, **http_request_kwargs())
        req.raise_for_status()
        data = req.json()
        country_code = data.get("address", {}).get("country_code")
        if country_code:
            return country_code.upper()
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        print(f"HTTP error for reverse geocoding ({latitude}, {longitude}): {e}")
    except (KeyError, ValueError):
        pass
    finally:
        time.sleep(1)  # Nominatim rate limit: 1 request/second
    return None


def get_fastly_data() -> list[dict]:
    """Fetch Fastly POP data and return location records."""
    resp = httpx.get(FASTLY_POP_URL, **http_request_kwargs())
    resp.raise_for_status()

    rows = extract_location_rows(resp.text)
    print(
        f"Found {len(rows)} POPs. Looking up countries with Nominatim. This might take a while."
    )

    locations = []
    for index, row in enumerate(rows, start=1):
        latitude, longitude = row["coordinates"]
        location = {
            "name": row["location"],
            "coordinates": [latitude, longitude],
            "siteCode": row["pop_code"],
        }
        print(f"  [{index}/{len(rows)}] {row['location']} ({row['pop_code']})")
        country_code = country_code_from_coordinates(latitude, longitude)
        if country_code:
            location["countryCode"] = country_code
        locations.append(location)

    return locations


if __name__ == "__main__":
    provider_name = "fastly"
    friendly_name = "Fastly"
    app_type = ["cdn"]

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
        fastly_data = get_fastly_data()
        geojson = convert_to_geojson([*fastly_data])
        geojson_data = geojson_skeleton(geojson)
        write_geojson_output(provider_name, geojson_data)

    write_and_post(
        provider_name,
        friendly_name,
        app_type,
        update_dev=args.dev,
        update_prod=args.prod,
    )
