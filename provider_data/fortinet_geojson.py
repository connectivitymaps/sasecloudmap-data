#!/usr/bin/env -S uv run
import argparse
import re
import sys
import time

import httpx
from bs4 import BeautifulSoup
from utils.geocoding import nominatim_get
from utils.http_config import http_request_kwargs
from utils.output import write_geojson_output
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
    for row in airport_codes:
        code = row["airport_code"]
        geometry = None
        try:
            geolocation = httpx.get(
                f"https://iata.clumsy.dev/?q={code.lower()}",
                **http_request_kwargs(),
            )
            resp = geolocation.json()
            if resp.get("success"):
                geometry = {
                    "name": row["name"],
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
                fallback_geolocation = nominatim_get(
                    f"https://nominatim.openstreetmap.org/search?format=geojson&polygon=1&addressdetails=1&limit=1&accept-language=en&q={code}+airport",
                    **http_request_kwargs(),
                )
                fallback_geolocation.raise_for_status()
                fallback_resp = fallback_geolocation.json()
                if fallback_resp.get("features"):
                    geometry = {
                        "name": row["name"],
                        "coordinates": fallback_resp["features"][0]["geometry"][
                            "coordinates"
                        ],
                    }
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                print(f"HTTP error for airport code {code}: {e}")
            except (KeyError, ValueError, IndexError) as e:
                print(f"Failed to parse airport code {code}: {e}")
            finally:
                time.sleep(1)  # Nominatim rate limit: 1 request/second

        if geometry:
            data.append(geometry)

    return [x for x in data if x]


def normalize_location_text(location_text: str) -> str:
    location_text = re.sub(r"\s+To comply\b.*$", "", location_text).strip()
    match = re.search(r".*\([A-Z]{3}-[A-Z0-9]+\)", location_text)
    if match:
        return match.group(0).strip()
    return location_text.strip()


def extract_location_rows(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    content = soup.find(id="mc-main-content")
    if content is None:
        raise ValueError("Could not find Fortinet content container")

    locations = content.select(
        "td.TableStyle-FortinetTable-BodyE-Column2-Body1, td.TableStyle-FortinetTable-BodyE-Column2-Body2"
    )

    rows = []
    for loc in locations:
        location_text = normalize_location_text(loc.get_text(" ", strip=True))
        if not location_text:
            continue
        match = re.search(r"\(([A-Z]{3})-[A-Z0-9]+\)", location_text)
        if match:
            rows.append({"name": location_text, "airport_code": match.group(1)})
    if rows:
        return rows

    for row in content.find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all("td")]
        if len(cells) < 3:
            continue

        location_text = normalize_location_text(cells[1])
        code_match = re.search(r"\b([A-Z]{3})-[A-Z0-9]+\b", cells[2])
        if not location_text or code_match is None:
            continue

        code = code_match.group(0)
        rows.append(
            {
                "name": f"{location_text} ({code})",
                "airport_code": code_match.group(1),
            }
        )
    return rows


def get_data():
    resp = httpx.get(
        "https://docs.fortinet.com/document/fortisase/latest/reference-guide/663044/global-data-centers",
        **http_request_kwargs(),
    )
    resp.raise_for_status()
    return extract_location_rows(resp.text)


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

        write_geojson_output(provider_name, geojson_data)

    write_and_post(
        provider_name,
        friendly_name,
        app_type,
        update_dev=args.dev,
        update_prod=args.prod,
    )
