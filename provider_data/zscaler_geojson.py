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
    """get data from zscaler"""
    locations = []
    resp = httpx.get(
        "https://config.zscaler.com/api/zscaler.net/cenr/json",
        **http_request_kwargs(),
    )
    resp.raise_for_status()
    data = resp.json()

    for continent in data["zscaler.net"]:
        for city, info in data["zscaler.net"][continent].items():
            locations.append(
                {
                    "name": city.removeprefix("city : "),
                    "coordinates": [info[0]["latitude"], info[0]["longitude"]],
                }
            )

    return locations


if __name__ == "__main__":
    provider_name = "zscaler"
    friendly_name = "Zscaler"
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
