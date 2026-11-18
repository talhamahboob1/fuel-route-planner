import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def build_session():
    config = settings.FUEL_ROUTER
    retries = int(config["HTTP_RETRIES"])
    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        backoff_factor=0.5,
        status_forcelist=(502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    session = requests.Session()
    session.headers["User-Agent"] = config["HTTP_USER_AGENT"]
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
