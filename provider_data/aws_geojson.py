#!/usr/bin/env -S uv run
import argparse
import json
import re
import sys
import time
from typing import TypedDict
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup
from utils.http_config import http_request_kwargs
from utils.base import convert_to_geojson
from utils.geocoding import nominatim_get
from utils.output import write_geojson_output
from utils.post_data import write_and_post
from utils.skeleton import geojson_skeleton

AWS_REGIONS_URL = "https://aws.amazon.com/about-aws/global-infrastructure/regions_az/"


class AwsRegion(TypedDict):
    name: str
    id: str
    lat: float
    lng: float
    available: bool


class LocationRecord(TypedDict, total=False):
    name: str
    coordinates: list[float]
    countryCode: str
    siteCode: str


def extract_aws_regions(html: str) -> list[AwsRegion]:
    """Parse AWS region records from the Global Infrastructure page.

    AWS embeds a per-region lat/lng dataset inside a ``<script
    type="application/json">`` tag used to drive the interactive region map.
    The payload is a JSON document whose ``fields.continents`` value is
    itself a JSON-encoded string (double-encoded), containing a list of
    continents, each with a ``regions`` list.
    """
    soup = BeautifulSoup(html, "html.parser")

    for script in soup.find_all("script", {"type": "application/json"}):
        if not script.string:
            continue
        try:
            payload = json.loads(script.string)
        except (json.JSONDecodeError, TypeError):
            continue

        items = (payload.get("data") or {}).get("items") or []
        for item in items:
            fields = item.get("fields") or {}
            continents_raw = fields.get("continents")
            if not continents_raw:
                continue
            try:
                continents = json.loads(continents_raw)
            except (json.JSONDecodeError, TypeError):
                continue

            regions: list[AwsRegion] = []
            for continent in continents:
                for region in continent.get("regions") or []:
                    if not all(
                        key in region
                        for key in ("name", "id", "lat", "lng", "available")
                    ):
                        continue
                    regions.append(
                        {
                            "name": region["name"].strip(),
                            "id": region["id"].strip(),
                            "lat": region["lat"],
                            "lng": region["lng"],
                            "available": region["available"],
                        }
                    )
            if regions:
                return regions

    raise ValueError("Could not find AWS region dataset")


def region_city_name(region_name: str) -> str:
    """Derive a short city/location label from AWS's region display name.

    AWS names regions like "US East (Northern Virginia)" or
    "Europe (Frankfurt)". Prefer the parenthesised location when present,
    falling back to the full name (e.g. "AWS GovCloud (US-East)" still
    yields "US-East").
    """
    match = re.search(r"\(([^)]+)\)", region_name)
    if match:
        return match.group(1).strip()
    return region_name.strip()


def geocode_country_code(lat: float, lng: float) -> str | None:
    """Reverse-geocode a lat/lng pair to an ISO-3166 alpha-2 country code."""
    url = (
        "https://nominatim.openstreetmap.org/reverse?"
        f"lat={quote_plus(str(lat))}&lon={quote_plus(str(lng))}"
        "&format=jsonv2&zoom=3&accept-language=en"
    )
    try:
        resp = nominatim_get(url, **http_request_kwargs())
        resp.raise_for_status()
        data = resp.json()
        country_code = (data.get("address") or {}).get("country_code")
        return country_code.upper() if country_code else None
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        print(f"HTTP error reverse-geocoding ({lat}, {lng}): {e}")
    except (KeyError, ValueError):
        pass
    finally:
        time.sleep(1)  # Nominatim rate limit: 1 request/second
    return None


def get_aws_data() -> list[dict]:
    """Fetch AWS region data and return location records.

    Only currently-available regions are included; AWS also lists
    announced-but-not-yet-launched regions (e.g. Chile, Saudi Arabia) in the
    same dataset, which are excluded here to match other providers showing
    live infrastructure only.
    """
    resp = httpx.get(
        AWS_REGIONS_URL,
        headers={"user-agent": "Mozilla/5.0"},
        **http_request_kwargs(),
    )
    resp.raise_for_status()

    regions = [
        region for region in extract_aws_regions(resp.text) if region["available"]
    ]
    print(
        f"Found {len(regions)} available AWS regions. Reverse-geocoding country codes."
    )

    locations: list[LocationRecord] = []
    for index, region in enumerate(regions, start=1):
        print(f"  [{index}/{len(regions)}] {region['name']} ({region['id']})")
        location: LocationRecord = {
            "name": region_city_name(region["name"]),
            "coordinates": [region["lat"], region["lng"]],
            "siteCode": region["id"],
        }
        country_code = geocode_country_code(region["lat"], region["lng"])
        if country_code:
            location["countryCode"] = country_code
        locations.append(location)

    return locations


if __name__ == "__main__":
    provider_name = "aws"
    friendly_name = "AWS (Amazon Web Services)"
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
        aws_data = get_aws_data()
        geojson = convert_to_geojson(aws_data)
        geojson_data = geojson_skeleton(geojson)
        write_geojson_output(provider_name, geojson_data)

    write_and_post(
        provider_name,
        friendly_name,
        app_type,
        update_dev=args.dev,
        update_prod=args.prod,
    )
