#!/usr/bin/env -S uv run
import argparse
import sys
import json
from bs4 import BeautifulSoup
import httpx
from lib.skeleton import geojson_skeleton
from lib.post_data import write_and_post


def convert_to_geojson(data):
    """convert passed data to proper geojson"""
    features = []

    for city in data:
        latitude, longitude = map(float, city["coordinates"])
        feature = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [latitude, longitude]},
            "properties": {"city": city["name"]},
        }
        features.append(feature)

    return features


def resolve_locations(locations):
    data = []
    for loc in locations:
        city_country = loc.split("-")
        city = city_country[0].strip()
        country = city_country[1].split(" (")[0].strip()
        geolocation = httpx.get(
            f"https://nominatim.openstreetmap.org/search?format=geojson&polygon=1&addressdetails=1&limit=1&q={city},{country}"
        )
        resp = geolocation.json()
        try:
            geometry = {
                "name": city,
                "coordinates": resp["features"][0]["geometry"]["coordinates"],
            }
            data.append(geometry)
        except IndexError:
            print(loc)

    return [x for x in data if x]


def get_data():
    colos = httpx.get(
        "https://docs.fortinet.com/document/fortisase/latest/reference-guide/663044/global-data-centers"
    )
    soup = BeautifulSoup(colos, "html.parser")
    content = soup.find(id="mc-main-content")
    table_body = content.find("tbody")
    rows = table_body.find_all("tr")

    data = []
    for row in rows:
        cols = row.find_all("td")
        cols = [ele.text.strip() for ele in cols]
        data.append(cols[1])

    return data


if __name__ == "__main__":
    provider_name = "fortisase"
    friendly_name = "Fortinet (FortiSASE)"
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
        geojson = resolve_locations(output)
        to_geosjon = convert_to_geojson(geojson)
        geojson_data = geojson_skeleton(to_geosjon)

        with open(f"output/{provider_name}.json", "w", encoding="utf-8") as f:
            json.dump(geojson_data, f, ensure_ascii=False)

    write_and_post(
        provider_name,
        friendly_name,
        app_type,
        update_dev=args.dev,
        update_prod=args.prod,
    )
