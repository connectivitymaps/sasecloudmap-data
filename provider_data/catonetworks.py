#!/usr/bin/env -S uv run
import argparse
import csv
import sys
import time
from io import StringIO
from urllib.parse import quote_plus

import httpx
from utils.base import convert_to_geojson
from utils.geocoding import nominatim_get
from utils.http_config import http_request_kwargs
from utils.output import write_geojson_output
from utils.post_data import write_and_post
from utils.skeleton import geojson_skeleton


COUNTRY_ALIASES = {
    "CAN": "Canada",
    "ECUA": "Ecuador",
    "MEX": "Mexico",
    "UAE": "United Arab Emirates",
    "UK": "United Kingdom",
}

LOCATION_ALIASES = {
    "Vancourver": "Vancouver",
}


def normalize_location_text(location_text: str) -> str:
    normalized = location_text.strip()
    if not normalized:
        return normalized

    for alias, replacement in LOCATION_ALIASES.items():
        normalized = normalized.replace(alias, replacement)

    parts = [part.strip() for part in normalized.split(",")]
    if parts and parts[-1] in COUNTRY_ALIASES:
        parts[-1] = COUNTRY_ALIASES[parts[-1]]
    return ", ".join(parts)


def extract_location_rows(csv_text: str) -> list[dict[str, str]]:
    csv_file = StringIO(csv_text)
    reader = csv.DictReader(csv_file, delimiter=",")
    locations = []
    for row in reader:
        pop_location = normalize_location_text(row.get("PoP\xa0Location", ""))
        serviced_through = normalize_location_text(
            row.get("Serviced Through (for Geo Location)", "")
        )
        region = (row.get("\ufeffRegion") or row.get("Region") or "").strip()

        if region == "Geo-Localized Ips" and serviced_through:
            geocode_query = serviced_through
            display_name = serviced_through
        else:
            geocode_query = pop_location
            display_name = pop_location

        if geocode_query:
            locations.append(
                {
                    "display_name": display_name,
                    "geocode_query": geocode_query,
                }
            )

    deduplicated = []
    seen_queries = set()
    for location in locations:
        query = location["geocode_query"]
        if query in seen_queries:
            continue
        seen_queries.add(query)
        deduplicated.append(location)
    return deduplicated


def get_data():
    resp = httpx.get(
        "https://support.catonetworks.com/hc/article_attachments/15675587976477",
        **http_request_kwargs(),
    )
    resp.raise_for_status()
    locations = []

    for location in extract_location_rows(resp.text):
        query = location["geocode_query"]
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
                    "name": location["display_name"],
                    "coordinates": [data[0]["lat"], data[0]["lon"]],
                }
            )
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            print(f"HTTP error for location {query}: {e}")
        except (KeyError, IndexError, ValueError) as e:
            print(f"Failed to parse location {query}: {e}")
        finally:
            time.sleep(1)  # Nominatim rate limit: 1 request/second

    return [i for n, i in enumerate(locations) if i not in locations[n + 1 :]]


if __name__ == "__main__":
    provider_name = "catonetworks"
    friendly_name = "Cato Networks"
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
