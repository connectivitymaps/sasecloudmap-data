#!/usr/bin/env -S uv run
import argparse
import json
import sys
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from utils.post_data import write_and_post
from utils.skeleton import geojson_skeleton


def get_data():
    data = httpx.get(
        "https://docs.paloaltonetworks.com/prisma/prisma-access/3-2/prisma-access-panorama-admin/prepare-the-prisma-access-infrastructure/list-of-prisma-access-locations/list-of-locations-by-compute-location"
    )
    data = data.text
    soup = BeautifulSoup(data, "html.parser")
    table = soup.select_one("#idf6de761e-2601-46d8-a61a-aaeb5e030069 > table")

    processed_location = []
    for row in table.tbody.find_all("tr"):
        cities = row.find_all("td")[2].get_text(separator="\n", strip=True).split("\n")
        processed_location.extend(cities)

    unique_locations = list(set(processed_location))
    locations = []

    for loc in unique_locations:
        req = httpx.get(
            "https://nominatim.openstreetmap.org/search?q={}&format=jsonv2&polygon=1&addressdetails=1&limit=1".format(
                quote_plus(loc)
            )
        )
        data = req.json()
        try:
            locations.append(
                {
                    "name": data[0]["place_id"],
                    "coordinates": [data[0]["lat"], data[0]["lon"]],
                }
            )
        except Exception as e:
            print(e)

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
    load_dotenv()
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

        with open(f"output/{provider_name}.json", "w", encoding="utf-8") as f:
            json.dump(geojson_data, f, ensure_ascii=False)

    write_and_post(
        provider_name,
        friendly_name,
        app_type,
        update_dev=args.dev,
        update_prod=args.prod,
    )
