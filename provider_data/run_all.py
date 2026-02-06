#!/usr/bin/env -S uv run
"""Run all provider scripts with graceful failure handling.
This script runs all provider update scripts and continues even if some fail.
"""

import argparse
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def extract_error_summary(stderr: str) -> tuple[str, str]:
    """Extract a clean error summary from stderr.

    Returns (short_error, full_error) tuple.
    """
    lines = stderr.strip().split("\n")

    # Look for common error patterns
    for line in reversed(lines):
        line = line.strip()
        # HTTP errors
        if "HTTPStatusError" in line or "status_code" in line:
            match = re.search(r"(\d{3}[^\n]*)", line)
            if match:
                return f"HTTP {match.group(1)}", stderr
        # Common Python errors at end of traceback
        if re.match(r"^(\w+Error|\w+Exception):", line):
            return line[:200], stderr
        # Playwright/browser errors
        if "playwright" in line.lower() and "error" in line.lower():
            return line[:200], stderr

    # Fallback: last non-empty line
    for line in reversed(lines):
        if line.strip():
            return line.strip()[:200], stderr

    return "Unknown error", stderr


def discover_providers() -> list[Path]:
    """Discover all provider scripts in the provider_data directory."""
    provider_dir = Path(__file__).parent
    providers = []
    for script in sorted(provider_dir.glob("*_geojson.py")):
        providers.append(script)
    # Also include scripts without _geojson suffix (like catonetworks.py)
    for script in sorted(provider_dir.glob("*.py")):
        if script.name not in ["run_all.py", "__init__.py"] and script not in providers:
            if not script.name.startswith("_"):
                providers.append(script)
    return providers


def run_provider(script_path: Path, refresh: bool, dev: bool, prod: bool) -> tuple[bool, str]:
    """Run a single provider script via subprocess.

    Returns (success, error_message).
    """
    cmd = ["uv", "run", str(script_path)]
    if refresh:
        cmd.append("--refresh")
    if dev:
        cmd.append("--dev")
    if prod:
        cmd.append("--prod")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=script_path.parent.parent,  # Run from repo root
        )
        if result.returncode != 0:
            stderr = result.stderr.strip() or result.stdout.strip() or "Unknown error"
            short_err, full_err = extract_error_summary(stderr)
            return False, (short_err, full_err)
        return True, None
    except Exception as e:
        err_msg = f"{type(e).__name__}: {e}"
        return False, (err_msg, err_msg)


def main():
    parser = argparse.ArgumentParser(
        description="Run all provider scripts with graceful failure handling."
    )
    parser.add_argument("--refresh", action="store_true", help="Refresh data from sources")
    parser.add_argument("--dev", action="store_true", help="Update dev environment")
    parser.add_argument("--prod", action="store_true", help="Update prod environment")
    parser.add_argument(
        "--provider",
        type=str,
        help="Run only specific provider (by name, without .py)",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Exit with error code on first failure",
    )

    args = parser.parse_args()

    if not (args.refresh or args.dev or args.prod):
        parser.print_help(sys.stderr)
        sys.exit(1)

    providers = discover_providers()

    if args.provider:
        providers = [p for p in providers if p.stem == args.provider]
        if not providers:
            print(f"❌ Provider '{args.provider}' not found")
            sys.exit(1)

    print(f"📋 Found {len(providers)} providers to update")
    print("-" * 50)

    results = {"success": [], "failed": []}

    # Run providers in parallel (max 5 concurrent to be respectful)
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(
                run_provider, script_path, args.refresh, args.dev, args.prod
            ): script_path
            for script_path in providers
        }

        for future in as_completed(futures):
            script_path = futures[future]
            provider_name = script_path.stem
            success, error = future.result()

            if success:
                print(f"✅ {provider_name}")
                results["success"].append(provider_name)
            else:
                short_err, full_err = error
                print(f"❌ {provider_name}: {short_err}")
                results["failed"].append((provider_name, short_err, full_err))

                if args.fail_fast:
                    print("\n💥 Fail-fast enabled, stopping")
                    executor.shutdown(wait=False, cancel_futures=True)
                    sys.exit(1)

    # Summary
    print("\n" + "=" * 50)
    print("📊 SUMMARY")
    print("=" * 50)
    print(f"✅ Successful: {len(results['success'])}")
    print(f"❌ Failed: {len(results['failed'])}")

    if results["failed"]:
        print("\n" + "-" * 50)
        print("FAILURE DETAILS")
        print("-" * 50)
        for name, short_err, full_err in results["failed"]:
            print(f"\n📌 {name}")
            print(f"   Error: {short_err}")
            # Show last 10 lines of traceback for context
            tb_lines = full_err.strip().split("\n")[-10:]
            for line in tb_lines:
                print(f"   {line}")

    # Always exit 0 unless fail-fast is enabled
    # This allows the CI pipeline to continue even with partial failures
    print("\n✨ Completed (exit 0 - partial failures are acceptable)")
    sys.exit(0)


if __name__ == "__main__":
    main()
