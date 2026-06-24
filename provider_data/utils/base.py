"""Base utilities for provider scripts."""


def location_from_nominatim_result(result: dict, fallback_name: str) -> dict:
    address = result.get("address") or {}
    name = (
        address.get("city")
        or address.get("town")
        or address.get("municipality")
        or address.get("village")
        or fallback_name
    )
    location = {
        "name": name,
        "coordinates": [result["lat"], result["lon"]],
    }
    country_code = address.get("country_code")
    if country_code:
        location["countryCode"] = country_code.upper()
    return location


def convert_to_geojson(data: list[dict]) -> list[dict]:
    """Convert location data to GeoJSON features.

    Expects data in format: [{"name": str, "coordinates": [lat, lon]}]
    Returns GeoJSON features with coordinates in [lon, lat] order.
    """
    features = []
    for city in data:
        latitude, longitude = map(float, city["coordinates"])
        properties = {"city": city["name"]}
        for key in ("countryCode", "siteCode"):
            if city.get(key):
                properties[key] = city[key]
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [round(longitude, 4), round(latitude, 4)],
            },
            "properties": properties,
        }
        features.append(feature)
    return features


def deduplicate(items: list) -> list:
    """Remove duplicates while preserving order (keeps first occurrence).

    For hashable items (strings), uses dict.fromkeys().
    For unhashable items (dicts), uses list comprehension.
    """
    if not items:
        return items
    if isinstance(items[0], dict):
        return [i for n, i in enumerate(items) if i not in items[n + 1 :]]
    return list(dict.fromkeys(items))
