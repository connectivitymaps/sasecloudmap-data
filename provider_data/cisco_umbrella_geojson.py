#!/usr/bin/env -S uv run
import argparse
import json
import sys
import time
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup
from utils.base import convert_to_geojson
from utils.http import http_request_kwargs
from utils.post_data import write_and_post
from utils.skeleton import geojson_skeleton


def extract_location_rows(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("#networks")
    if table is None:
        raise ValueError("Could not find Cisco Umbrella locations table")

    rows = []
    for row in table.find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all("td")]
        if len(cells) < 2:
            continue
        rows.append({"location": cells[0], "facility": cells[1]})
    return rows


def build_geocode_queries(location: str, facility: str) -> list[str]:
    candidates = []
    if facility:
        candidates.append(f"{facility}, {location}")
    candidates.append(location)
    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


def get_data():
    """get data from cisco"""
    resp = httpx.get(
        "https://umbrella.cisco.com/why-umbrella/global-network-and-traffic",
        **http_request_kwargs(),
    )
    resp.raise_for_status()

    locations = []

    for row in extract_location_rows(resp.text):
        for query in build_geocode_queries(row["location"], row["facility"]):
            try:
                req = httpx.get(
                    "https://nominatim.openstreetmap.org/search?q={}&format=jsonv2&polygon=1&addressdetails=1&limit=1&accept-language=en".format(
                        quote_plus(query)
                    ),
                    **http_request_kwargs(),
                )
                req.raise_for_status()
                data = req.json()
                locations.append(
                    {
                        "name": row["location"],
                        "coordinates": [data[0]["lat"], data[0]["lon"]],
                    }
                )
                break
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                print(f"HTTP error for location {query}: {e}")
            except (KeyError, IndexError, ValueError):
                continue
            finally:
                time.sleep(1)  # Nominatim rate limit: 1 request/second
    return locations


if __name__ == "__main__":
    provider_name = "cisco"
    friendly_name = "Cisco Umbrella"
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
