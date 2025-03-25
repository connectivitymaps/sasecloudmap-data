import httpx
import os
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()
headers = {
    "auth": os.environ["AUTH"],
    "content-type": "application/json",
}

url = os.environ["DEV_HOSTNAME"]
parsed_url = urlparse(url)
base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

dev = httpx.get(
    f"{base_url}/sitemap",
    headers=headers,
)
print(dev.text)
