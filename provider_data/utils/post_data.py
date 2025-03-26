import httpx
import json
import os
from urllib.parse import urlparse
from dotenv import load_dotenv


def write_and_post(
    provider_name,
    friendly_name,
    app_type,
    update_dev=False,
    update_prod=False,
):
    load_dotenv()
    headers = {
        "auth": os.environ["AUTH"],
        "content-type": "application/json",
        "bms": os.environ["BMS"],
    }
    payload = {}
    payload["friendlyName"] = friendly_name
    payload["appType"] = app_type

    if update_dev:
        with open(f"output/{provider_name}.json") as f:
            payload["data"] = json.load(f)
            dev = httpx.post(
                f"{os.environ['DEV_HOSTNAME']}{provider_name}",
                headers=headers,
                json=payload,
            )
            print(f"dev update: {dev.text}")
    if update_prod:
        url = os.environ["DEV_HOSTNAME"]
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        dev = httpx.get(
            f"{base_url}/api/{provider_name}",
            headers={"bms": os.environ["BMS"]},
        )
        payload["data"] = dev.json()
        prod = httpx.post(
            f"{os.environ['PROD_HOSTNAME']}{provider_name}",
            headers=headers,
            json=payload,
        )
        print(f"prod update: {prod.text}")
