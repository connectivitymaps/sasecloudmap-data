"""Base utilities for provider scripts."""


def convert_to_geojson(data: list[dict]) -> list[dict]:
    """Convert location data to GeoJSON features.

    Expects data in format: [{"name": str, "coordinates": [lat, lon]}]
    Returns GeoJSON features with coordinates in [lon, lat] order.
    """
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
