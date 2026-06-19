#!/usr/bin/env -S uv run
import argparse
import re
import sys
import time
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup
from utils.base import convert_to_geojson
from utils.geocoding import nominatim_get
from utils.http_config import http_request_kwargs
from utils.output import write_geojson_output
from utils.post_data import write_and_post
from utils.skeleton import geojson_skeleton


COUNTRY_ALIASES = {
    "UK": "United Kingdom",
    "USA": "United States",
}


def normalize_location_text(text: str) -> str:
    return re.sub(r"\s*\(\d+\)\s*$", "", text).strip()


def build_geocode_queries(location_text: str) -> list[str]:
    parts = [part.strip() for part in location_text.split(",")]
    if not parts:
        return []

    parts[0] = re.sub(r"\s+\d+$", "", parts[0]).strip()
    if parts[-1] in COUNTRY_ALIASES:
        parts[-1] = COUNTRY_ALIASES[parts[-1]]

    query = ", ".join(part for part in parts if part)
    return [query] if query else []


def extract_checkpoint_locations(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("#mc-main-content table") or soup.select_one("table")
    if table is None:
        raise ValueError("Could not find Check Point locations table")

    processed_locations = []
    for item in table.find_all("li"):
        location = normalize_location_text(item.get_text(" ", strip=True))
        if location:
            processed_locations.append(location)
    return list(dict.fromkeys(processed_locations))


def get_data():
    resp = httpx.get(
        "https://sc1.checkpoint.com/documents/Infinity_Portal/WebAdminGuides/EN/SASE-Admin-Guide/Content/Topics-SASE-AG/Networks/Regions-PoP.htm",
        **http_request_kwargs(),
    )
    resp.raise_for_status()
    locations = []

    for loc in extract_checkpoint_locations(resp.text):
        for query in build_geocode_queries(loc):
            try:
                req = nominatim_get(
                    "https://nominatim.openstreetmap.org/search?q={}&format=jsonv2&polygon=1&addressdetails=1&limit=1&accept-language=en".format(
                        quote_plus(query)
                    ),
                    **http_request_kwargs(),
                )
                req.raise_for_status()
                data = req.json()
                locations.append(
                    {
                        "name": loc,
                        "coordinates": [data[0]["lat"], data[0]["lon"]],
                    }
                )
                break
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                print(f"HTTP error for location {query}: {e}")
            except (KeyError, IndexError, ValueError) as e:
                print(f"Failed to parse location {query}: {e}")
            finally:
                time.sleep(1)  # Nominatim rate limit: 1 request/second

    return locations


if __name__ == "__main__":
    provider_name = "checkpoint"
    friendly_name = "Check Point Harmony"
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

        write_geojson_output(provider_name, geojson_data)

    write_and_post(
        provider_name,
        friendly_name,
        app_type,
        update_dev=args.dev,
        update_prod=args.prod,
    )
