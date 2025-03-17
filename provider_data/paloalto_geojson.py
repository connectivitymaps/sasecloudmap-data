#!/usr/bin/env -S uv run
import argparse
import sys
import json
import os
from dotenv import load_dotenv
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
import httpx
from lib.skeleton import geojson_skeleton
from lib.post_data import write_and_post


def prompt_location(location):
    prompt = f"which is the largest city with an airport in {location}, please respond only with the city name and country. if the input is already a city, just respond with the initial input again. respond with absolutely nothing else, also no acknowledgement."
    req = httpx.post(
        f"https://api.cloudflare.com/client/v4/accounts/{os.environ['CLOUDFLARE_ACCOUNT_ID']}/ai/run/@cf/meta/llama-3.3-70b-instruct-fp8-fast",
        headers={"Authorization": f"Bearer {os.environ['CLOUDFLARE_API_TOKEN']}"},
        json={
            "messages": [
                {"role": "system", "content": "You are a friendly assistant"},
                {"role": "user", "content": prompt},
            ]
        },
    )
    result = req.json()
    return result["result"]["response"]


def get_data():
    data = httpx.get(
        "https://docs.paloaltonetworks.com/prisma/prisma-access/3-2/prisma-access-panorama-admin/prepare-the-prisma-access-infrastructure/list-of-prisma-access-locations/list-of-locations-by-region"
    )
    data = data.text
    soup = BeautifulSoup(data, "html.parser")
    table = soup.select_one("#id089612c2-6bca-417d-8e99-f2af7c5a44fc > table")

    processed_location = []
    for ele in table.find_all("td"):
        text = ele.text.strip()
        if not text.endswith("Region"):
            processed_location.append(text)

    unique_locations = list(set(processed_location))
    locations = []

    for loc in unique_locations:
        loc_data = prompt_location(loc)
        req = httpx.get(
            "https://nominatim.openstreetmap.org/search?q={}&format=jsonv2&polygon=1&addressdetails=1&limit=1".format(
                quote_plus(loc_data)
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
