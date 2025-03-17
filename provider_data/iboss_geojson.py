#!/usr/bin/env -S uv run
import argparse
import sys
import json
from urllib.parse import quote_plus
import httpx
from utils.skeleton import geojson_skeleton
from utils.post_data import write_and_post


def get_data():
    """get cloudflare locations"""
    colos = httpx.get(
        "https://status.iboss.com/ibcloud/web/public/cloudStatus/dataCenters"
    )
    colos = colos.json()

    colos = [
        item["name"].replace(" POP", "") for region in colos.values() for item in region
    ]
    locations = []
    for colo in colos:
        req = httpx.get(
            f"https://nominatim.openstreetmap.org/search?q={quote_plus(colo)}&format=jsonv2&polygon=1&addressdetails=1&limit=1"
        )
        output = req.json()
        locations.append(
            {
                "name": output[0]["name"],
                "coordinates": [output[0]["lat"], output[0]["lon"]],
            }
        )

    return locations


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

        with open(f"output/{provider_name}.json", "w", encoding="utf-8") as f:
            json.dump(geojson_data, f, ensure_ascii=False)

    write_and_post(
        provider_name,
        friendly_name,
        app_type,
        update_dev=args.dev,
        update_prod=args.prod,
    )
