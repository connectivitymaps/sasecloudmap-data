import argparse
import os
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

load_dotenv()


def main():
    parser = argparse.ArgumentParser(
        description="Generate sitemap for specified environment"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prod", action="store_true", help="Use production hostname")
    group.add_argument("--dev", action="store_true", help="Use development hostname")

    args = parser.parse_args()

    headers = {
        "auth": os.environ["AUTH"],
        "content-type": "application/json",
    }

    if args.prod:
        url = os.environ["PROD_HOSTNAME"]
    else:  # args.dev
        url = os.environ["DEV_HOSTNAME"]

    parsed_url = urlparse(url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    cache_host = parsed_url.hostname

    # Update sitemap
    resp = httpx.get(
        f"{base_url}/sitemap",
        headers=headers,
    )
    print(f"updating {base_url}: {resp.text}")

    # Clear cache
    cache_headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {os.environ['CACHE_PURGE_KEY']}",
    }

    cache_data = {"hosts": [cache_host]}

    zone_id = os.environ["CLOUDFLARE_ZONE_ID"]
    cache_resp = httpx.post(
        f"https://api.cloudflare.com/client/v4/zones/{zone_id}/purge_cache",
        headers=cache_headers,
        json=cache_data,
    )
    print(f"clearing cache for {cache_host}: {cache_resp.text}")


if __name__ == "__main__":
    main()
