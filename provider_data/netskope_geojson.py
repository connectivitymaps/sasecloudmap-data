#!/usr/bin/env -S uv run
import argparse
import sys

import httpx
from utils.base import convert_to_geojson
from utils.http_config import http_request_kwargs
from utils.output import write_geojson_output
from utils.post_data import write_and_post
from utils.skeleton import geojson_skeleton


def get_data():
    resp = httpx.get(
        "https://trust.netskope.com/ss/v1/datacenters",
        **http_request_kwargs(),
    )
    resp.raise_for_status()
    data = resp.json()
    data = [loc for loc in data if loc.get("is_dp") is True]

    locations = []
    seen = set()

    for loc in data:
        location_key = loc["name"]
        if location_key not in seen:
            seen.add(location_key)
            locations.append(
                {
                    "name": loc["name"],
                    "coordinates": [
                        loc["latitude"],
                        loc["longitude"],
                    ],
                }
            )

    return locations


if __name__ == "__main__":
    provider_name = "netskope"
    friendly_name = "Netskope"
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
