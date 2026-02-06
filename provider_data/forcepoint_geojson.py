#!/usr/bin/env -S uv run
import argparse
import json
import sys
import time

import httpx
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from utils.post_data import write_and_post
from utils.skeleton import geojson_skeleton


def get_data():
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch()
    page = browser.new_page()
    page.goto(
        "https://support.forcepoint.com/s/article/Cloud-service-data-center-IP-addresses-port-numbers"
    )
    page.wait_for_load_state("networkidle")
    # Find the table containing COUNTRY and CITY columns
    tables = page.locator("table").all()
    html = None
    for table in tables:
        content = table.inner_html()
        if "COUNTRY" in content and "CITY" in content:
            html = content
            break
    if not html:
        raise ValueError("Could not find data center locations table")
    browser.close()
    playwright.stop()

    soup = BeautifulSoup(html, "html.parser")
    headers = [th.text.strip() for th in soup.find_all("th")]
    desired_columns = ["COUNTRY", "CITY"]
    column_indices = [headers.index(col) for col in desired_columns]

    data = []
    for row in soup.find_all("tr")[1:]:
        cells = row.find_all("td")
        row_data = [cells[i].text.strip() for i in column_indices]
        data.append(row_data)

    locations = []
    for row in data:
        city, country = row[-1], row[0]
        try:
            geolocation = httpx.get(
                f"https://nominatim.openstreetmap.org/search?format=geojson&polygon=1&addressdetails=1&limit=1&q={city},{country}"
            )
            geolocation.raise_for_status()
            resp = geolocation.json()
            geometry = {
                "name": city,
                "coordinates": resp["features"][0]["geometry"]["coordinates"],
            }
            locations.append(geometry)
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            print(f"HTTP error for location {city}, {country}: {e}")
        except (KeyError, IndexError, ValueError) as e:
            print(f"Failed to parse location {city}, {country}: {e}")
        finally:
            time.sleep(1)  # Nominatim rate limit: 1 request/second

    return locations


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


if __name__ == "__main__":
    provider_name = "forcepoint"
    friendly_name = "Forcepoint"
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
