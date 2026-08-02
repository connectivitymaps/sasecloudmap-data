#!/usr/bin/env -S uv run
import argparse
import re
import sys
import time
from typing import TypedDict
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup
from bs4.element import NavigableString
from utils.base import convert_to_geojson
from utils.geocoding import nominatim_get
from utils.http_config import http_request_kwargs
from utils.output import write_geojson_output
from utils.post_data import write_and_post
from utils.skeleton import geojson_skeleton

AWS_CLOUDFRONT_URL = (
    "https://aws.amazon.com/cloudfront/features/#points-of-presence-pops"
)


class PopRow(TypedDict):
    region: str
    country: str
    city: str


class LocationRecord(TypedDict, total=False):
    name: str
    coordinates: list[str]
    countryCode: str


def split_cities(cities_text: str) -> list[str]:
    """Split a comma-separated city list and strip counts from each entry."""
    parts = []
    for entry in cities_text.split(","):
        entry = re.sub(r"\s*(?:\(\d+\)|\d+\))\s*$", "", entry)
        entry = entry.strip()
        if entry:
            parts.append(entry)
    return parts


def parse_city_name(entry: str) -> str | None:
    """Return a cleaned city name, or None if empty."""
    entry = entry.strip().rstrip(",")
    if not entry:
        return None
    return entry


def split_malformed_country_block(
    country: str, cities_text: str
) -> list[tuple[str, str]]:
    """Handle malformed/concatenated country blocks like 'LisbonRomania: Bucharest (3)'.

    Returns a list of (country, cities_text) tuples.
    """
    pattern = re.compile(r"([A-Z][a-z\s]{1,30}):\s*")
    matches = list(pattern.finditer(cities_text))
    if not matches:
        return [(country, cities_text)]

    results = []
    if matches[0].start() > 0:
        results.append((country, cities_text[: matches[0].start()]))

    for index, match in enumerate(matches):
        new_country = match.group(1).strip()
        start = match.end()
        end = (
            matches[index + 1].start() if index + 1 < len(matches) else len(cities_text)
        )
        results.append((new_country, cities_text[start:end]))

    return results


def text_after_bold(paragraph) -> str:
    """Return all text in the paragraph after the first <b> tag."""
    bold = paragraph.find("b")
    if bold is None:
        return ""

    parts = []
    sibling = bold.next_sibling
    while sibling:
        if isinstance(sibling, NavigableString):
            parts.append(str(sibling))
        else:
            parts.append(sibling.get_text(" "))
        sibling = sibling.next_sibling
    return "".join(parts).strip()


def extract_pop_rows(html: str) -> list[PopRow]:
    """Parse AWS CloudFront PoP cities from the page HTML."""
    soup = BeautifulSoup(html, "html.parser")
    section = soup.find("div", id="points-of-presence-pops")
    if section is None:
        raise ValueError("Could not find AWS Points of Presence section")

    body_div = section.find("div", {"data-rg-n": "BodyText"})
    if body_div is None:
        raise ValueError("Could not find AWS PoP body text container")

    rows = []
    current_region = ""
    started = False

    for paragraph in body_div.find_all("p", recursive=False):
        text = paragraph.get_text(" ", strip=True)
        if not text or text == "\u00a0":
            continue

        if text.startswith("Embedded Points of Presence"):
            break

        bold = paragraph.find("b")
        if bold is None:
            continue

        bold_text = bold.get_text(strip=True)
        after_bold = text_after_bold(paragraph)

        if not after_bold:
            region_name = bold_text.rstrip(":").strip()
            if region_name == "North America" or started:
                current_region = region_name
                started = True
            continue

        if not started:
            continue

        country = bold_text.rstrip(":").strip()

        if re.fullmatch(r"\(\d+\)", after_bold):
            # Special case: <b>Singapore</b> (12)
            city = parse_city_name(country)
            if city:
                rows.append(
                    {
                        "region": current_region,
                        "country": country,
                        "city": city,
                    }
                )
            continue

        blocks = split_malformed_country_block(country, after_bold)
        for block_country, block_cities in blocks:
            for entry in split_cities(block_cities):
                city = parse_city_name(entry)
                if city:
                    rows.append(
                        {
                            "region": current_region,
                            "country": block_country,
                            "city": city,
                        }
                    )

    return rows


def geocode_city(city: str, country: str) -> LocationRecord | None:
    """Geocode a city with Nominatim and return a location record."""
    query = f"{city}, {country}"
    url = (
        "https://nominatim.openstreetmap.org/search?"
        f"q={quote_plus(query)}"
        "&format=jsonv2&polygon=1&addressdetails=1&limit=1&accept-language=en"
    )
    try:
        req = nominatim_get(url, **http_request_kwargs())
        req.raise_for_status()
        data = req.json()
        result = data[0]
        address = result.get("address") or {}
        location: LocationRecord = {
            "name": city,
            "coordinates": [result["lat"], result["lon"]],
        }
        country_code = address.get("country_code")
        if country_code:
            location["countryCode"] = country_code.upper()
        return location
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        print(f"HTTP error for location {query}: {e}")
    except (KeyError, IndexError, ValueError):
        pass
    finally:
        time.sleep(1)  # Nominatim rate limit: 1 request/second
    return None


def get_aws_data() -> list[dict]:
    """Fetch AWS CloudFront PoP data and return location records."""

    resp = httpx.get(AWS_CLOUDFRONT_URL, **http_request_kwargs())
    resp.raise_for_status()

    rows = extract_pop_rows(resp.text)
    print(f"Found {len(rows)} PoPs. Geocoding with Nominatim. This may take a while.")

    locations = []
    for index, row in enumerate(rows, start=1):
        print(f"  [{index}/{len(rows)}] {row['city']}, {row['country']}")
        location = geocode_city(row["city"], row["country"])
        if location is None:
            print(f"    Skipping {row['city']}: geocoding failed")
            continue
        locations.append(location)

    print(f"Done. Geocoded {len(locations)}/{len(rows)} PoPs.")
    return locations


if __name__ == "__main__":
    provider_name = "aws"
    friendly_name = "AWS CloudFront"
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
        geojson = convert_to_geojson([*aws_data])
        geojson_data = geojson_skeleton(geojson)
        write_geojson_output(provider_name, geojson_data)

    write_and_post(
        provider_name,
        friendly_name,
        app_type,
        update_dev=args.dev,
        update_prod=args.prod,
    )
