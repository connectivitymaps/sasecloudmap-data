import os
import ssl
from functools import lru_cache
from pathlib import Path

import certifi
from dotenv import load_dotenv


EXTRA_CA_CERT_FILE_ENV = "EXTRA_CA_CERT_FILE"
RELAX_X509_STRICT_ENV = "RELAX_X509_STRICT"


@lru_cache(maxsize=1)
def http_request_kwargs() -> dict:
    load_dotenv()
    extra_ca_path = os.getenv(EXTRA_CA_CERT_FILE_ENV, "").strip()
    if not extra_ca_path:
        return {}

    extra_ca_file = Path(extra_ca_path).expanduser()
    if not extra_ca_file.is_file():
        raise FileNotFoundError(
            f"{EXTRA_CA_CERT_FILE_ENV} does not exist: {extra_ca_file}"
        )

    ssl_context = ssl.create_default_context(cafile=certifi.where())
    ssl_context.load_verify_locations(cafile=str(extra_ca_file))
    if os.getenv(RELAX_X509_STRICT_ENV, "").strip().lower() in {"1", "true", "yes"}:
        ssl_context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return {"verify": ssl_context}
