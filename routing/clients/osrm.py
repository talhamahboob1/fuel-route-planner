import logging

import requests
from django.conf import settings

from ..exceptions import ExternalServiceError, RouteNotFound
from ..polyline import decode_polyline
from ..types import Route
from .http import build_session

logger = logging.getLogger(__name__)

NO_ROUTE_CODES = {"NoRoute", "NoSegment", "InvalidQuery", "InvalidValue", "InvalidOptions"}


class OSRMClient:
    def __init__(self, base_url=None, timeout=None, session=None):
        config = settings.FUEL_ROUTER
        self.base_url = (base_url or config["OSRM_BASE_URL"]).rstrip("/")
        self.timeout = timeout or config["HTTP_TIMEOUT_SECONDS"]
        self.user_agent = config["HTTP_USER_AGENT"]
        self.session = session or build_session()

    def route(self, start, finish):
        path = f"{start.longitude:.6f},{start.latitude:.6f};{finish.longitude:.6f},{finish.latitude:.6f}"
        url = f"{self.base_url}/route/v1/driving/{path}"
        params = {
            "overview": "full",
            "geometries": "polyline",
            "steps": "false",
            "alternatives": "false",
            "annotations": "false",
        }
        try:
            response = self.session.get(
                url, params=params, timeout=self.timeout, headers={"User-Agent": self.user_agent}
            )
        except requests.RequestException as exc:
            logger.warning("OSRM request failed: %s", exc)
            raise ExternalServiceError("routing", "The routing service could not be reached.") from exc

        if response.status_code == 429:
            raise ExternalServiceError(
                "routing", "The routing service is rate limiting requests, please retry shortly."
            )
        try:
            payload = response.json()
        except ValueError as exc:
            logger.warning("OSRM returned a non JSON response with status %s", response.status_code)
            raise ExternalServiceError("routing", "The routing service returned an unreadable response.") from exc

        code = payload.get("code")
        if code != "Ok":
            message = payload.get("message") or code or "unknown error"
            if code in NO_ROUTE_CODES:
                raise RouteNotFound(f"No drivable route was found between the two locations ({message}).")
            raise ExternalServiceError("routing", f"The routing service returned an error: {message}.")

        routes = payload.get("routes") or []
        if not routes:
            raise RouteNotFound("No drivable route was found between the two locations.")
        route = routes[0]
        geometry = route.get("geometry")
        if not isinstance(geometry, str) or not geometry:
            raise ExternalServiceError("routing", "The routing service returned a route without geometry.")
        try:
            coordinates = tuple(decode_polyline(geometry))
        except ValueError as exc:
            raise ExternalServiceError("routing", "The routing service returned an unreadable geometry.") from exc
        return Route(
            distance_meters=float(route["distance"]),
            duration_seconds=float(route["duration"]),
            coordinates=coordinates,
        )
