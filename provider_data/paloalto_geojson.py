#!/usr/bin/env -S uv run
import argparse
import sys
import time
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup
from utils.base import convert_to_geojson, location_from_nominatim_result
from utils.geocoding import nominatim_get
from utils.http_config import http_request_kwargs
from utils.output import write_geojson_output
from utils.post_data import write_and_post
from utils.skeleton import geojson_skeleton


def find_locations_table(soup: BeautifulSoup):
    expected_headers = [
        "compute location",
        "prisma access location",
        "city and country",
    ]
    for table in soup.find_all("table"):
        headers = [
            header.get_text(" ", strip=True).lower() for header in table.find_all("th")
        ]
        if all(header in headers for header in expected_headers):
            return table
    return None


def extract_paloalto_locations(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    table = find_locations_table(soup)
    if table is None:
        raise ValueError("Could not find Palo Alto locations table")

    processed_locations = []
    rows = (
        table.tbody.find_all("tr") if table.tbody is not None else table.find_all("tr")
    )
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        cities = cells[2].get_text(separator="\n", strip=True).split("\n")
        processed_locations.extend(city for city in cities if city)
    return list(dict.fromkeys(processed_locations))


def get_data():
    resp = httpx.get(
        "https://docs.paloaltonetworks.com/prisma-access/administration/prisma-access-overview/list-of-prisma-access-locations",
        **http_request_kwargs(),
    )
    resp.raise_for_status()
    locations = []

    for loc in extract_paloalto_locations(resp.text):
        try:
            req = nominatim_get(
                "https://nominatim.openstreetmap.org/search?q={}&format=jsonv2&polygon=1&addressdetails=1&limit=1&accept-language=en".format(
                    quote_plus(loc)
                ),
                **http_request_kwargs(),
            )
            req.raise_for_status()
            data = req.json()
            locations.append(location_from_nominatim_result(data[0], loc))
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            print(f"HTTP error for location {loc}: {e}")
        except (KeyError, IndexError, ValueError) as e:
            print(f"Failed to parse location {loc}: {e}")
        finally:
            time.sleep(1)  # Nominatim rate limit: 1 request/second

    return locations


if __name__ == "__main__":
    provider_name = "paloalto"
    friendly_name = "Prisma Access (PANW)"
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
