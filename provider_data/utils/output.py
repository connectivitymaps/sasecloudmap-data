"""Output safety helpers for provider GeoJSON files."""

import json
from pathlib import Path


def validate_geojson_output(
    provider_name: str,
    data: dict,
    *,
    empty_action: str = "has",
    min_features: int = 1,
) -> None:
    """Validate provider GeoJSON before writing or posting it."""
    if not isinstance(data, dict):
        raise ValueError(f"{provider_name} output must be a GeoJSON object")
    if data.get("type") != "FeatureCollection":
        raise ValueError(f"{provider_name} output must be a FeatureCollection")

    features = data.get("features")
    if not isinstance(features, list):
        raise ValueError(f"{provider_name} output features must be a list")
    if len(features) < min_features:
        raise ValueError(
            f"{provider_name} {empty_action} {len(features)} features; "
            "refusing empty provider data"
        )


def write_geojson_output(
    provider_name: str,
    data: dict,
    *,
    output_dir: str | Path = "output",
    min_features: int = 1,
) -> Path:
    """Validate and atomically write a provider GeoJSON output file."""
    validate_geojson_output(
        provider_name,
        data,
        empty_action="produced",
        min_features=min_features,
    )

    output_path = Path(output_dir) / f"{provider_name}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_suffix(f"{output_path.suffix}.tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False)
    temp_path.replace(output_path)
    return output_path
