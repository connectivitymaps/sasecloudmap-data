#!/usr/bin/env -S uv run
import argparse
import sys
import time
from typing import TypedDict

import httpx
from utils.base import convert_to_geojson
from utils.geocoding import nominatim_get
from utils.http_config import http_request_kwargs
from utils.output import write_geojson_output
from utils.post_data import write_and_post
from utils.skeleton import geojson_skeleton

GOOGLE_CLOUD_CDN_URL = "https://cloud-dot-devsite-v2-prod.appspot.com/about/locations/cloud_cdn_markers.json"


class Marker(TypedDict):
    lat: float
    lng: float
    label: str


class ParsedLabel(TypedDict):
    city: str
    state: str
    country: str


class LocationRecord(TypedDict, total=False):
    name: str
    coordinates: list[float]
    countryCode: str


def parse_label(label: str) -> ParsedLabel:
    """Split a Google Cloud CDN marker label into city, state, and country.

    Supports labels like 'City, Country' and 'City, State, Country'.
    """
    parts = [part.strip() for part in label.split(",")]
    if len(parts) == 2:
        return {"city": parts[0], "state": "", "country": parts[1]}
    if len(parts) >= 3:
        return {"city": parts[0], "state": parts[1], "country": parts[2]}
    return {"city": label, "state": "", "country": ""}


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


def get_googlecloud_data() -> list[dict]:
    """Fetch Google Cloud CDN marker data and return location records."""

    resp = httpx.get(GOOGLE_CLOUD_CDN_URL, **http_request_kwargs())
    resp.raise_for_status()

    markers: list[Marker] = resp.json()
    print(
        f"Found {len(markers)} markers. Looking up countries with Nominatim. This may take a while."
    )

    locations = []
    for index, marker in enumerate(markers, start=1):
        parsed = parse_label(marker["label"])
        latitude = marker["lat"]
        longitude = marker["lng"]
        print(f"  [{index}/{len(markers)}] {parsed['city']} ({marker['label']})")
        location: LocationRecord = {
            "name": parsed["city"],
            "coordinates": [latitude, longitude],
        }
        country_code = country_code_from_coordinates(latitude, longitude)
        if country_code:
            location["countryCode"] = country_code
        locations.append(location)

    return locations


if __name__ == "__main__":
    provider_name = "googlecloud"
    friendly_name = "Google Cloud CDN"
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
        googlecloud_data = get_googlecloud_data()
        geojson = convert_to_geojson([*googlecloud_data])
        geojson_data = geojson_skeleton(geojson)
        write_geojson_output(provider_name, geojson_data)

    write_and_post(
        provider_name,
        friendly_name,
        app_type,
        update_dev=args.dev,
        update_prod=args.prod,
    )
