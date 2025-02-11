#!/usr/bin/env -S uv run
import argparse
import sys
import json
import re
import httpx
from provider_data.lib.skeleton import geojson_skeleton
from provider_data.lib.post_data import write_and_post


def get_cloudflare_data():
    """get cloudflare locations"""
    colos = httpx.get("https://speed.cloudflare.com/locations")
    colos = colos.json()

    locations = []
    for colo in colos:
        locations.append(
            {"name": colo["city"], "coordinates": [colo["lat"], colo["lon"]]}
        )

    return [i for n, i in enumerate(locations) if i not in locations[n + 1 :]]


def get_jdcloud_data():
    """get cloudflare jd cloud specific locations"""
    china_colos = httpx.get("https://api.cloudflare.com/client/v4/ips?networks=jdcloud")
    data = china_colos.json()
    data = data["result"]["jdcloud_cidrs"]

    china_cidrs = [re.sub(r"/.*$", "", line) for line in data]

    locations = []
    for cidr in china_cidrs:
        ip_geolocation = httpx.get("https://ipinfo.io/{}".format(cidr))
        data = ip_geolocation.json()
        locations.append({"name": data["city"], "coordinates": data["loc"].split(",")})

    return [i for n, i in enumerate(locations) if i not in locations[n + 1 :]]


def convert_to_geojson(data):
    """convert passed data to proper geojson"""
    features = []

    for city in data:
        latitude, longitude = map(float, city["coordinates"])
        feature = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
            "properties": {"city": city["name"]},
        }
        features.append(feature)
    return features


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
