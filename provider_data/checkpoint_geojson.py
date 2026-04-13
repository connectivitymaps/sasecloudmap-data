#!/usr/bin/env -S uv run
import argparse
import json
import re
import sys
import time
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup
from utils.base import convert_to_geojson
from utils.http import http_request_kwargs
from utils.post_data import write_and_post
from utils.skeleton import geojson_skeleton


def normalize_location_text(text: str) -> str:
    return re.sub(r"\s*\(\d+\)\s*$", "", text).strip()


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
        try:
            req = httpx.get(
                "https://nominatim.openstreetmap.org/search?q={}&format=jsonv2&polygon=1&addressdetails=1&limit=1&accept-language=en".format(
                    quote_plus(loc)
                ),
                **http_request_kwargs(),
            )
            req.raise_for_status()
            data = req.json()
            locations.append(
                {
                    "name": data[0]["name"],
                    "coordinates": [data[0]["lat"], data[0]["lon"]],
                }
            )
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            print(f"HTTP error for location {loc}: {e}")
        except (KeyError, IndexError, ValueError) as e:
            print(f"Failed to parse location {loc}: {e}")
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

        with open(f"output/{provider_name}.json", "w", encoding="utf-8") as f:
            json.dump(geojson_data, f, ensure_ascii=False)

    write_and_post(
        provider_name,
        friendly_name,
        app_type,
        update_dev=args.dev,
        update_prod=args.prod,
    )
