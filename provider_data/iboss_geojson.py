#!/usr/bin/env -S uv run
import argparse
import re
import sys
import time
from urllib.parse import quote_plus

import httpx
from utils.base import convert_to_geojson
from utils.geocoding import nominatim_get
from utils.http_config import http_request_kwargs
from utils.output import write_geojson_output
from utils.post_data import write_and_post
from utils.skeleton import geojson_skeleton


def normalize_pop_location(name: str) -> str:
    return re.sub(r"\s+POP(?:\s+\d+)?$", "", name).strip()


def get_data():
    """get iboss locations"""
    resp = httpx.get(
        "https://status.iboss.com/ibcloud/web/public/cloudStatus/dataCenters",
        **http_request_kwargs(),
    )
    resp.raise_for_status()
    colos = resp.json()

    colos = [
        normalize_pop_location(item["name"])
        for region in colos.values()
        for item in region
    ]
    locations = []
    for colo in colos:
        try:
            req = nominatim_get(
                f"https://nominatim.openstreetmap.org/search?q={quote_plus(colo)}&format=jsonv2&polygon=1&addressdetails=1&limit=1&accept-language=en",
                **http_request_kwargs(),
            )
            req.raise_for_status()
            output = req.json()
            locations.append(
                {
                    "name": output[0]["name"],
                    "coordinates": [output[0]["lat"], output[0]["lon"]],
                }
            )
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            print(f"HTTP error for location {colo}: {e}")
        except (KeyError, IndexError, ValueError) as e:
            print(f"Failed to parse location {colo}: {e}")
        finally:
            time.sleep(1)  # Nominatim rate limit: 1 request/second

    return locations


if __name__ == "__main__":
    provider_name = "iboss"
    friendly_name = "iboss"
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
