#!/usr/bin/env -S uv run
import argparse
import csv
import json
import sys
import time
from io import StringIO
from urllib.parse import quote_plus

import httpx
from utils.base import convert_to_geojson
from utils.http_config import http_request_kwargs
from utils.post_data import write_and_post
from utils.skeleton import geojson_skeleton


def extract_location_queries(csv_text: str) -> list[str]:
    csv_file = StringIO(csv_text)
    reader = csv.DictReader(csv_file, delimiter=",")
    queries = []
    for row in reader:
        query = (
            row.get("Serviced Through (for Geo Location)", "").strip()
            or row["PoP\xa0Location"].strip()
        )
        if query:
            queries.append(query)
    return list(dict.fromkeys(queries))


def get_data():
    resp = httpx.get(
        "https://support.catonetworks.com/hc/article_attachments/15675587976477",
        **http_request_kwargs(),
    )
    resp.raise_for_status()
    locations = []

    for pop in extract_location_queries(resp.text):
        try:
            req = httpx.get(
                "https://nominatim.openstreetmap.org/search?q={}&format=jsonv2&polygon=1&addressdetails=1&limit=1&accept-language=en".format(
                    quote_plus(pop)
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
            print(f"HTTP error for location {pop}: {e}")
        except (KeyError, IndexError, ValueError) as e:
            print(f"Failed to parse location {pop}: {e}")
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

        with open(f"output/{provider_name}.json", "w", encoding="utf-8") as f:
            json.dump(geojson_data, f, ensure_ascii=False)

    write_and_post(
        provider_name,
        friendly_name,
        app_type,
        update_dev=args.dev,
        update_prod=args.prod,
    )
