#!/usr/bin/env -S uv run
import argparse
import json
import re
import sys

import httpx
from bs4 import BeautifulSoup
from utils.post_data import write_and_post
from utils.skeleton import geojson_skeleton


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


def resolve_locations(airport_codes):
    """resolve airport codes to geolocation"""
    data = []
    for code in airport_codes:
        geometry = None
        try:
            geolocation = httpx.get(f"https://iata.clumsy.dev/?q={code.lower()}")
            resp = geolocation.json()
            if resp.get("success"):
                geometry = {
                    "name": resp["name"],
                    "coordinates": [resp["lon"], resp["lat"]],
                }
            else:
                pass
        except (KeyError, ValueError, httpx.RequestError) as e:
            print(
                f"API failed for airport code: {code}, error: {e}, trying fallback..."
            )
        if geometry is None:
            try:
                fallback_geolocation = httpx.get(
                    f"https://nominatim.openstreetmap.org/search?format=geojson&polygon=1&addressdetails=1&limit=1&q={code}+airport"
                )
                fallback_resp = fallback_geolocation.json()
                if fallback_resp.get("features"):
                    geometry = {
                        "name": f"{code} Airport",
                        "coordinates": fallback_resp["features"][0]["geometry"][
                            "coordinates"
                        ],
                    }
                else:
                    pass
            except (KeyError, ValueError, httpx.RequestError) as e:
                print(
                    f"could not find coordinates for airport code: {code}, error: {e}"
                )

        if geometry:
            data.append(geometry)

    return [x for x in data if x]


def get_data():
    colos = httpx.get(
        "https://docs.fortinet.com/document/fortisase/latest/reference-guide/663044/global-data-centers"
    )
    soup = BeautifulSoup(colos.text, "html.parser")
    content = soup.find(id="mc-main-content")
    locations = content.select(
        "td.TableStyle-FortinetTable-BodyE-Column2-Body1, td.TableStyle-FortinetTable-BodyE-Column2-Body2"
    )

    airport_codes = []
    for loc in locations:
        location_text = loc.get_text(strip=True)
        if location_text and (" - " in location_text or "(" in location_text):
            match = re.search(r"\(([A-Z]{3})-", location_text)
            if match:
                airport_code = match.group(1)
                airport_codes.append(airport_code)

    unique_codes = list(dict.fromkeys(airport_codes))
    return unique_codes


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
