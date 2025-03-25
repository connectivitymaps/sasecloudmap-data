import httpx
import json
import os
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
        dev = httpx.get(f"{os.environ['DEV_HOSTNAME']}{provider_name}")
        payload["data"] = dev.json()
        prod = httpx.post(
            f"{os.environ['PROD_HOSTNAME']}{provider_name}",
            headers=headers,
            json=payload,
        )
        print(f"prod update: {prod.text}")
