import httpx
import os
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()
headers = {
    "auth": os.environ["AUTH"],
    "content-type": "application/json",
}

urls = [os.environ["DEV_HOSTNAME"], os.environ["PROD_HOSTNAME"]]
for url in urls:
    parsed_url = urlparse(url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

    resp = httpx.get(
        f"{base_url}/sitemap",
        headers=headers,
    )
    print(f"updating {base_url}: {resp.text}")
