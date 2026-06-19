#!/usr/bin/env -S uv run
"""Run all provider scripts with graceful failure handling.
This script runs all provider update scripts and continues even if some fail.
"""

import argparse
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from builtins import input
from pathlib import Path

from provider_data.utils.provider_discovery import (
    discover_provider_scripts,
    extract_provider_name,
    select_provider_scripts,
)


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
        # Browser automation / rendering errors
        if (
            any(
                phrase in line.lower()
                for phrase in ["browser rendering", "browser-rendering", "quick action"]
            )
            and "error" in line.lower()
        ):
            return line[:200], stderr

    # Fallback: last non-empty line
    for line in reversed(lines):
        if line.strip():
            return line.strip()[:200], stderr

    return "Unknown error", stderr


def discover_providers() -> list[Path]:
    """Discover all provider scripts in the provider_data directory."""
    return discover_provider_scripts(Path(__file__).parent)


def max_workers_for_run(refresh: bool) -> int:
    """Return worker count for provider fan-out."""
    if refresh:
        return 1
    return 3


def run_provider(
    script_path: Path, refresh: bool, dev: bool, prod: bool
) -> tuple[bool, str]:
    """Run a single provider script via subprocess.

    Returns (success, error_message).
    """
    cmd = [sys.executable, str(script_path)]
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


def remove_failed_refresh_output(script_path: Path) -> Path | None:
    """Delete partial output written by a provider that failed during refresh."""
    provider_name = extract_provider_name(script_path)
    if provider_name is None:
        return None

    output_path = Path("output") / f"{provider_name}.json"
    if not output_path.exists():
        return None

    output_path.unlink()
    return output_path


def sitemap_targets(dev: bool, prod: bool) -> list[str]:
    """Return sitemap environments requested by provider update flags."""
    targets = []
    if dev:
        targets.append("dev")
    if prod:
        targets.append("prod")
    return targets


def run_sitemap(target: str) -> None:
    """Run sitemap generation for a single environment."""
    script_path = Path(__file__).parent / "utils" / "generate_sitemap.py"
    subprocess.run(
        [sys.executable, str(script_path), f"--{target}"],
        check=True,
        cwd=script_path.parent.parent.parent,
    )


def should_generate_sitemap(args: argparse.Namespace, targets: list[str]) -> bool:
    """Decide whether to generate sitemap after provider processing."""
    if not targets or args.skip_sitemap:
        return False
    if args.generate_sitemap:
        return True
    if not sys.stdin.isatty():
        print("Skipping sitemap generation in non-interactive mode.")
        return False

    target_text = " and ".join(targets)
    answer = input(f"Generate sitemap for {target_text}? [y/N] ")
    return answer.strip().lower() in {"y", "yes"}


def main():
    parser = argparse.ArgumentParser(
        description="Run all provider scripts with graceful failure handling."
    )
    parser.add_argument(
        "--refresh", action="store_true", help="Refresh data from sources"
    )
    parser.add_argument("--dev", action="store_true", help="Update dev environment")
    parser.add_argument("--prod", action="store_true", help="Update prod environment")
    parser.add_argument(
        "--provider",
        type=str,
        help="Run only a specific provider (script stem or declared provider_name)",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Exit with error code on first failure",
    )
    parser.add_argument(
        "--fail-on-any-failure",
        action="store_true",
        help="Exit with error code after processing all providers if any failed",
    )
    sitemap_group = parser.add_mutually_exclusive_group()
    sitemap_group.add_argument(
        "--generate-sitemap",
        action="store_true",
        help="Generate sitemap for --dev and/or --prod without prompting",
    )
    sitemap_group.add_argument(
        "--skip-sitemap",
        action="store_true",
        help="Do not prompt for or generate sitemap",
    )

    args = parser.parse_args()

    if not (args.refresh or args.dev or args.prod):
        parser.print_help(sys.stderr)
        sys.exit(1)

    providers = discover_providers()

    if args.provider:
        providers = select_provider_scripts(providers, args.provider)
        if not providers:
            print(f"❌ Provider '{args.provider}' not found")
            sys.exit(1)

    print(f"📋 Found {len(providers)} providers to update")
    print("-" * 50)

    results = {"success": [], "failed": []}

    # Refreshes may perform bulk geocoding; keep those single-threaded across
    # providers so their per-script throttling is not defeated by fan-out.
    max_workers = max_workers_for_run(args.refresh)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
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

                if args.refresh:
                    removed_output = remove_failed_refresh_output(script_path)
                    if removed_output is not None:
                        print(f"🧹 Removed partial output: {removed_output}")

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

    if results["failed"] and args.fail_on_any_failure:
        print("\n💥 Completed with provider failures (exit 1)")
        sys.exit(1)

    targets = sitemap_targets(args.dev, args.prod)
    if should_generate_sitemap(args, targets):
        for target in targets:
            print(f"\n🗺️ Generating {target} sitemap")
            run_sitemap(target)

    # Always exit 0 unless fail-fast or fail-on-any-failure is enabled.
    # This allows the CI pipeline to continue even with partial failures.
    print("\n✨ Completed (exit 0 - partial failures are acceptable)")
    sys.exit(0)


if __name__ == "__main__":
    main()
