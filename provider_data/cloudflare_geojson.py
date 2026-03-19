#!/usr/bin/env -S uv run
import argparse
import json
import re
import sys

import httpx
from utils.base import convert_to_geojson
from utils.post_data import write_and_post
from utils.skeleton import geojson_skeleton


def get_cloudflare_data():
    """get cloudflare locations"""
    resp = httpx.get("https://speed.cloudflare.com/locations", headers={"referer": "https://speed.cloudflare.com/"})
    resp.raise_for_status()
    colos = resp.json()

    locations = []
    for colo in colos:
        locations.append(
            {"name": colo["iata"], "coordinates": [colo["lat"], colo["lon"]]}
        )

    return [i for n, i in enumerate(locations) if i not in locations[n + 1 :]]


def get_jdcloud_data():
    """get cloudflare jd cloud specific locations"""
    resp = httpx.get("https://api.cloudflare.com/client/v4/ips?networks=jdcloud")
    resp.raise_for_status()
    data = resp.json()
    data = data["result"]["jdcloud_cidrs"]

    china_cidrs = [re.sub(r"/.*$", "", line) for line in data]

    locations = []
    for cidr in china_cidrs:
        try:
            ip_geolocation = httpx.get("https://ipinfo.io/{}".format(cidr))
            ip_geolocation.raise_for_status()
            geo_data = ip_geolocation.json()
            locations.append({"name": geo_data["city"], "coordinates": geo_data["loc"].split(",")})
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            print(f"HTTP error for CIDR {cidr}: {e}")
        except (KeyError, ValueError) as e:
            print(f"Failed to parse CIDR {cidr}: {e}")

    return [i for n, i in enumerate(locations) if i not in locations[n + 1 :]]


if __name__ == "__main__":
    provider_name = "cloudflare"
    friendly_name = "Cloudflare"
    app_type = ["sase", "cdn"]

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
        cloudflare_data = get_cloudflare_data()
        cloudflare_jd_data = get_jdcloud_data()
        geojson = convert_to_geojson([*cloudflare_data, *cloudflare_jd_data])
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
