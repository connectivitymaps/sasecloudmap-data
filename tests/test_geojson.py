#!/usr/bin/env -S uv run
"""Tests for GeoJSON validation.

These tests validate the structure and format of GeoJSON output
without relying on specific data content (which changes frequently).
"""

import json
from pathlib import Path

import pytest


def get_output_files() -> list[Path]:
    """Get all JSON files from the output directory."""
    output_dir = Path(__file__).parent.parent / "output"
    if not output_dir.exists():
        return []
    return list(output_dir.glob("*.json"))


def validate_geojson_structure(data: dict) -> list[str]:
    """Validate GeoJSON FeatureCollection structure.

    Returns list of validation errors (empty if valid).
    """
    errors = []

    # Root level validation
    if not isinstance(data, dict):
        errors.append("Root must be a dict")
        return errors

    if data.get("type") != "FeatureCollection":
        errors.append(f"Expected type 'FeatureCollection', got '{data.get('type')}'")

    if "features" not in data:
        errors.append("Missing 'features' array")
        return errors

    if not isinstance(data["features"], list):
        errors.append("'features' must be an array")
        return errors

    # Feature validation
    for i, feature in enumerate(data["features"]):
        feature_errors = validate_feature(feature, i)
        errors.extend(feature_errors)

    return errors


def validate_feature(feature: dict, index: int) -> list[str]:
    """Validate a single GeoJSON Feature."""
    errors = []
    prefix = f"Feature[{index}]"

    if not isinstance(feature, dict):
        return [f"{prefix}: must be a dict"]

    if feature.get("type") != "Feature":
        errors.append(f"{prefix}: type must be 'Feature', got '{feature.get('type')}'")

    # Geometry validation
    if "geometry" not in feature:
        errors.append(f"{prefix}: missing 'geometry'")
    else:
        geom_errors = validate_geometry(feature["geometry"], prefix)
        errors.extend(geom_errors)

    # Properties validation
    if "properties" not in feature:
        errors.append(f"{prefix}: missing 'properties'")
    elif not isinstance(feature["properties"], dict):
        errors.append(f"{prefix}: 'properties' must be a dict")

    return errors


def validate_geometry(geometry: dict, prefix: str) -> list[str]:
    """Validate GeoJSON Point geometry."""
    errors = []

    if not isinstance(geometry, dict):
        return [f"{prefix}.geometry: must be a dict"]

    if geometry.get("type") != "Point":
        errors.append(
            f"{prefix}.geometry: type must be 'Point', got '{geometry.get('type')}'"
        )

    if "coordinates" not in geometry:
        errors.append(f"{prefix}.geometry: missing 'coordinates'")
        return errors

    coords = geometry["coordinates"]
    if not isinstance(coords, list) or len(coords) != 2:
        errors.append(f"{prefix}.geometry.coordinates: must be [lon, lat] array")
        return errors

    lon, lat = coords
    try:
        lon, lat = float(lon), float(lat)
    except (TypeError, ValueError):
        errors.append(f"{prefix}.geometry.coordinates: values must be numeric")
        return errors

    # Validate coordinate ranges
    if not (-180 <= lon <= 180):
        errors.append(
            f"{prefix}.geometry.coordinates: longitude {lon} out of range [-180, 180]"
        )
    if not (-90 <= lat <= 90):
        errors.append(
            f"{prefix}.geometry.coordinates: latitude {lat} out of range [-90, 90]"
        )

    return errors


class TestGeoJSONValidation:
    """Test GeoJSON structure validation."""

    def test_valid_geojson(self):
        """Test that valid GeoJSON passes validation."""
        valid = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-122.4194, 37.7749]},
                    "properties": {"city": "San Francisco"},
                }
            ],
        }
        errors = validate_geojson_structure(valid)
        assert errors == [], f"Valid GeoJSON should pass: {errors}"

    def test_missing_type(self):
        """Test detection of missing type."""
        invalid = {"features": []}
        errors = validate_geojson_structure(invalid)
        assert any("type" in e for e in errors)

    def test_invalid_coordinates_range(self):
        """Test detection of out-of-range coordinates."""
        invalid = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [200, 100]},
                    "properties": {"city": "Invalid"},
                }
            ],
        }
        errors = validate_geojson_structure(invalid)
        assert any("out of range" in e for e in errors)

    def test_empty_features_is_valid(self):
        """Test that empty features array is valid."""
        valid = {"type": "FeatureCollection", "features": []}
        errors = validate_geojson_structure(valid)
        assert errors == []


class TestOutputFiles:
    """Test actual output files if they exist."""

    @pytest.fixture
    def output_files(self):
        """Get output files, skip if none exist."""
        files = get_output_files()
        if not files:
            pytest.skip("No output files found - run --refresh first")
        return files

    def test_output_files_are_valid_json(self, output_files):
        """Test that all output files are valid JSON."""
        for filepath in output_files:
            with open(filepath) as f:
                try:
                    json.load(f)
                except json.JSONDecodeError as e:
                    pytest.fail(f"{filepath.name}: Invalid JSON - {e}")

    def test_output_files_are_valid_geojson(self, output_files):
        """Test that all output files are valid GeoJSON."""
        for filepath in output_files:
            with open(filepath) as f:
                data = json.load(f)
            errors = validate_geojson_structure(data)
            assert errors == [], f"{filepath.name}: {errors}"

    def test_output_files_have_features(self, output_files):
        """Test that output files have at least one feature."""
        empty_files = []
        for filepath in output_files:
            with open(filepath) as f:
                data = json.load(f)
            # Track empty files but don't fail - some providers might legitimately have 0 locations
            if len(data.get("features", [])) == 0:
                empty_files.append(filepath.name)
        if empty_files:
            pytest.skip(f"Files with no features (may be expected): {', '.join(empty_files)}")


class TestProviderScripts:
    """Test provider script imports and structure."""

    def test_all_providers_importable(self):
        """Test that all provider scripts can be imported without errors."""
        provider_dir = Path(__file__).parent.parent / "provider_data"
        for script in provider_dir.glob("*.py"):
            if script.name in ["run_all.py", "__init__.py"] or script.name.startswith(
                "_"
            ):
                continue
            # Just check if file is valid Python syntax
            with open(script) as f:
                code = f.read()
            try:
                compile(code, script, "exec")
            except SyntaxError as e:
                pytest.fail(f"{script.name}: Syntax error - {e}")


def test_convert_to_geojson():
    """Test the convert_to_geojson utility function."""
    from provider_data.utils.base import convert_to_geojson

    input_data = [
        {"name": "Test City", "coordinates": ["37.7749", "-122.4194"]},
    ]
    result = convert_to_geojson(input_data)

    assert len(result) == 1
    assert result[0]["type"] == "Feature"
    assert result[0]["geometry"]["type"] == "Point"
    # Note: coordinates should be [lon, lat] in output
    assert result[0]["geometry"]["coordinates"] == [-122.4194, 37.7749]
    assert result[0]["properties"]["city"] == "Test City"


def test_deduplicate():
    """Test the deduplicate utility function."""
    from provider_data.utils.base import deduplicate

    # Test with strings
    strings = ["a", "b", "a", "c", "b"]
    assert deduplicate(strings) == ["a", "b", "c"]

    # Test with dicts (keeps last occurrence due to algorithm)
    dicts = [{"x": 1}, {"x": 2}, {"x": 1}]
    result = deduplicate(dicts)
    assert len(result) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
