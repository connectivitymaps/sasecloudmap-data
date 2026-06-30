#!/usr/bin/env -S uv run
import argparse
import sys
import time
from typing import TypedDict
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup
from utils.base import convert_to_geojson
from utils.geocoding import nominatim_get
from utils.http_config import http_request_kwargs
from utils.output import write_geojson_output
from utils.post_data import write_and_post
from utils.skeleton import geojson_skeleton

ORACLE_REGIONS_URL = (
    "https://docs.oracle.com/en-us/iaas/Content/General/Concepts/regions.htm"
)


class RegionRow(TypedDict):
    region_name: str
    region_location: str
    region_key: str


class LocationRecord(TypedDict, total=False):
    name: str
    coordinates: list[str]
    countryCode: str
    siteCode: str


def parse_region_location(location: str) -> tuple[str, str]:
    """Split a region location into city and remainder (state or country).

    Examples:
        "Sydney, Australia" -> ("Sydney", "Australia")
        "Ashburn, VA" -> ("Ashburn", "VA")
        "Jovanovac,Serbia" -> ("Jovanovac", "Serbia")
    """
    parts = location.split(",", maxsplit=1)
    city = parts[0].strip()
    remainder = parts[1].strip() if len(parts) > 1 else ""
    return city, remainder


def extract_region_rows(html: str) -> list[RegionRow]:
    """Parse Oracle region rows from the documentation HTML.

    Finds the table whose first header cell reads "Region Name" and returns
    rows with the region name, location, and region key.
    """
    soup = BeautifulSoup(html, "html.parser")

    table = None
    for candidate in soup.find_all("table"):
        header = candidate.find("thead")
        if header is None:
            continue
        first_header = header.find("th")
        if first_header and first_header.get_text(strip=True) == "Region Name":
            table = candidate
            break

    if table is None:
        raise ValueError("Could not find Oracle regions table")

    tbody = table.find("tbody")
    if tbody is None:
        raise ValueError("Could not find Oracle regions table body")

    rows = []
    for row in tbody.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 4:
            continue

        region_name = cells[0].get_text(" ", strip=True)
        region_location = cells[2].get_text(" ", strip=True)
        region_key = cells[3].get_text(" ", strip=True)

        if not region_name or not region_location or not region_key:
            continue

        rows.append(
            {
                "region_name": region_name,
                "region_location": region_location,
                "region_key": region_key,
            }
        )
    return rows


def geocode_region_location(
    region_location: str, fallback_city: str
) -> LocationRecord | None:
    """Geocode a region location with Nominatim and return a location record."""
    url = (
        "https://nominatim.openstreetmap.org/search?"
        f"q={quote_plus(region_location)}"
        "&format=jsonv2&polygon=1&addressdetails=1&limit=1&accept-language=en"
    )
    try:
        req = nominatim_get(url, **http_request_kwargs())
        req.raise_for_status()
        data = req.json()
        result = data[0]
        address = result.get("address") or {}
        location: LocationRecord = {
            "name": fallback_city,
            "coordinates": [result["lat"], result["lon"]],
        }
        country_code = address.get("country_code")
        if country_code:
            location["countryCode"] = country_code.upper()
        return location
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        print(f"HTTP error for location {region_location}: {e}")
    except (KeyError, IndexError, ValueError):
        pass
    finally:
        time.sleep(1)  # Nominatim rate limit: 1 request/second
    return None


def get_oracle_data() -> list[dict]:
    """Fetch Oracle region data and return location records."""

    resp = httpx.get(ORACLE_REGIONS_URL, **http_request_kwargs())
    resp.raise_for_status()

    rows = extract_region_rows(resp.text)
    print(
        f"Found {len(rows)} regions. Geocoding with Nominatim. This might take a while."
    )

    locations = []
    for index, row in enumerate(rows, start=1):
        city, _ = parse_region_location(row["region_location"])
        print(f"  [{index}/{len(rows)}] {row['region_name']} ({row['region_key']})")
        location = geocode_region_location(row["region_location"], city)
        if location is None:
            print(f"    Skipping {row['region_name']}: geocoding failed")
            continue
        location["siteCode"] = row["region_key"]
        locations.append(location)

    return locations


if __name__ == "__main__":
    provider_name = "oracle"
    friendly_name = "Oracle Cloud Infrastructure"
    app_type = ["cloud"]

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
        oracle_data = get_oracle_data()
        geojson = convert_to_geojson([*oracle_data])
        geojson_data = geojson_skeleton(geojson)
        write_geojson_output(provider_name, geojson_data)

    write_and_post(
        provider_name,
        friendly_name,
        app_type,
        update_dev=args.dev,
        update_prod=args.prod,
    )
