"""Helpers for discovering provider scripts and provider output names."""

import argparse
import ast
import json
from pathlib import Path


def _extract_string_constant(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def extract_provider_name(script_path: Path) -> str | None:
    """Extract a provider's output filename stem from its script."""
    try:
        tree = ast.parse(script_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            value = _extract_string_constant(node.value)
            if value is None:
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "provider_name":
                    return value
        elif isinstance(node, ast.AnnAssign):
            value = _extract_string_constant(node.value)
            if (
                value is not None
                and isinstance(node.target, ast.Name)
                and node.target.id == "provider_name"
            ):
                return value
    return None


def discover_provider_scripts(provider_dir: Path | None = None) -> list[Path]:
    """Discover all provider scripts in the provider_data directory."""
    if provider_dir is None:
        provider_dir = Path(__file__).resolve().parent.parent

    providers = []
    geojson_scripts = sorted(provider_dir.glob("*_geojson.py"))
    providers.extend(geojson_scripts)

    for script in sorted(provider_dir.glob("*.py")):
        if script.name in {"run_all.py", "__init__.py"}:
            continue
        if script.name.startswith("_"):
            continue
        if script in providers:
            continue
        providers.append(script)

    return providers


def _build_provider_records(provider_dir: Path | None = None) -> list[dict[str, str]]:
    """Build provider metadata records from the current provider scripts."""
    records = []
    for script_path in discover_provider_scripts(provider_dir):
        provider_name = extract_provider_name(script_path)
        if provider_name is None:
            raise ValueError(
                f"Unable to discover provider_name from {script_path.name}; "
                "provider_name must be a literal top-level string assignment."
            )
        records.append(
            {
                "script": script_path.stem,
                "provider_name": provider_name,
                "output_file": f"{provider_name}.json",
            }
        )
    return records


def discover_expected_files(provider_dir: Path | None = None) -> set[str]:
    """Discover the output JSON files expected from the current provider scripts."""
    return {
        record["output_file"] for record in _build_provider_records(provider_dir)
    }


def discover_provider_records(provider_dir: Path | None = None) -> list[dict[str, str]]:
    """Discover provider script metadata for workflow generation."""
    return _build_provider_records(provider_dir)


def select_provider_scripts(providers: list[Path], selector: str) -> list[Path]:
    """Select provider scripts by either script stem or declared provider name."""
    matched = [provider for provider in providers if provider.stem == selector]
    if matched:
        return matched

    return [
        provider
        for provider in providers
        if extract_provider_name(provider) == selector
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover provider workflow records")
    parser.add_argument("--provider-dir", default="provider_data")
    parser.add_argument("--github-output", default=None)
    args = parser.parse_args()

    records = discover_provider_records(Path(args.provider_dir))
    if args.github_output:
        with Path(args.github_output).open("a", encoding="utf-8") as fh:
            fh.write(f"providers={json.dumps(records)}\n")
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
