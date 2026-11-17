import logging
from dataclasses import dataclass

import requests
from django.conf import settings

from ..exceptions import ExternalServiceError
from ..types import Coordinate

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GeocodedPlace:
    coordinate: Coordinate
    display_name: str


class NominatimClient:
    def __init__(self, base_url=None, timeout=None, session=None):
        config = settings.FUEL_ROUTER
        self.base_url = (base_url or config["NOMINATIM_BASE_URL"]).rstrip("/")
        self.timeout = timeout or config["HTTP_TIMEOUT_SECONDS"]
        self.user_agent = config["HTTP_USER_AGENT"]
        self.session = session or requests.Session()

    def geocode(self, query):
        params = {"q": query, "format": "jsonv2", "limit": 1, "countrycodes": "us"}
        try:
            response = self.session.get(
                f"{self.base_url}/search",
                params=params,
                timeout=self.timeout,
                headers={"User-Agent": self.user_agent, "Accept-Language": "en"},
            )
        except requests.RequestException as exc:
            logger.warning("Nominatim request failed: %s", exc)
            raise ExternalServiceError("geocoding", "The geocoding service could not be reached.") from exc

        if response.status_code == 429:
            raise ExternalServiceError(
                "geocoding", "The geocoding service is rate limiting requests, please retry shortly."
            )
        if not response.ok:
            raise ExternalServiceError("geocoding", f"The geocoding service returned status {response.status_code}.")
        try:
            results = response.json()
        except ValueError as exc:
            raise ExternalServiceError("geocoding", "The geocoding service returned an unreadable response.") from exc
        if not results:
            return None
        first = results[0]
        return GeocodedPlace(
            coordinate=Coordinate(latitude=float(first["lat"]), longitude=float(first["lon"])),
            display_name=first.get("display_name") or query,
        )
