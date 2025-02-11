#!/usr/bin/env -S uv run
import argparse
import sys
import json
import re
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
import httpx
from provider_data.lib.skeleton import geojson_skeleton
from provider_data.lib.post_data import write_and_post


def get_data():
    data = httpx.get("https://trust.netskope.com/")
    data = data.text
    soup = BeautifulSoup(data, "html.parser")

    pattern_parentheses = re.compile(r"\(.*?\)")
    pattern_asterisk = re.compile(r"\*")
    processed_location = []

    for ele in soup.find_all("span", class_="name"):
        text = ele.text.strip()
        if "(" in text and ")" in text:
            cleaned_text = pattern_parentheses.sub("", text).strip()
            cleaned_text = cleaned_text.encode("latin-1", "ignore").decode("latin-1")
            cleaned_text = pattern_asterisk.sub("", cleaned_text).strip()
            processed_location.append(cleaned_text)

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

        with open(f"output/{provider_name}.json", "w", encoding="utf-8") as f:
            json.dump(geojson_data, f, ensure_ascii=False)

    write_and_post(
        provider_name,
        friendly_name,
        app_type,
        update_dev=args.dev,
        update_prod=args.prod,
    )
