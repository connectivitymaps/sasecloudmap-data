#!/usr/bin/env -S uv run
import argparse
import json
import sys
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import httpx
from lib.skeleton import geojson_skeleton
from lib.post_data import write_and_post


def get_data():
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch()
    page = browser.new_page()
    page.goto(
        "https://support.forcepoint.com/s/article/Cloud-service-data-center-IP-addresses-port-numbers"
    )
    location = page.locator(
        "css=#ServiceCommunityTemplate > div.cCenterPanel > div > div.slds-grid.slds-wrap.slds-medium-nowrap.slds-large-nowrap > div.slds-col--padded.slds-size--12-of-12.slds-medium-size--8-of-12.slds-large-size--8-of-12.comm-layout-column > div > div:nth-child(1) > c-hub_-knowledge-article-page > div:nth-child(6) > div > div.slds-form-element__control.slds-grid.itemBody > span > span > table:nth-child(7)"
    )
    location.scroll_into_view_if_needed()
    html = location.inner_html()
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
        geolocation = httpx.get(
            f"https://nominatim.openstreetmap.org/search?format=geojson&polygon=1&addressdetails=1&limit=1&q={city},{country}"
        )
        resp = geolocation.json()
        try:
            geometry = {
                "name": city,
                "coordinates": resp["features"][0]["geometry"]["coordinates"],
            }
            locations.append(geometry)
        except Exception:
            pass

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
