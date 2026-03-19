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
from utils.post_data import write_and_post
from utils.skeleton import geojson_skeleton


def get_data():
    resp = httpx.get(
        "https://support.catonetworks.com/hc/article_attachments/15675587976477"
    )
    resp.raise_for_status()
    pops = []
    csv_file = StringIO(resp.text)
    reader = csv.DictReader(csv_file, delimiter=",")
    for row in reader:
        pops.append(row["PoP\xa0Location"].strip())

    locations = []

    for pop in list(dict.fromkeys(pops)):
        try:
            req = httpx.get(
                "https://nominatim.openstreetmap.org/search?q={}&format=jsonv2&polygon=1&addressdetails=1&limit=1".format(
                    quote_plus(pop)
                )
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
