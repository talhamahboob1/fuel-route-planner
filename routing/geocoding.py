import logging
import re
from dataclasses import dataclass

from stations.gazetteer import get_gazetteer
from stations.us_states import normalize_state

from .clients.nominatim import NominatimClient
from .exceptions import LocationNotFound, LocationOutsideUSA
from .models import GeocodeCacheEntry
from .types import Coordinate
from .usa import is_within_usa

logger = logging.getLogger(__name__)

COORDINATE_PATTERN = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)\s*$")
COUNTRY_SUFFIXES = {"USA", "US", "U S", "U S A", "UNITED STATES", "UNITED STATES OF AMERICA"}


@dataclass(frozen=True)
class ResolvedLocation:
    query: str
    label: str
    coordinate: Coordinate
    source: str


def parse_coordinates(text):
    match = COORDINATE_PATTERN.match(text)
    if not match:
        return None
    latitude, longitude = float(match.group(1)), float(match.group(2))
    if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
        raise LocationNotFound(f"'{text}' is not a valid latitude, longitude pair.", query=text)
    return Coordinate(latitude=latitude, longitude=longitude)


def split_city_state(text):
    cleaned = text.strip()
    if "," in cleaned:
        head, _, tail = cleaned.rpartition(",")
        tail_key = " ".join(tail.replace(".", " ").split()).upper()
        if tail_key in COUNTRY_SUFFIXES:
            return split_city_state(head)
        state = normalize_state(tail)
        if state and head.strip():
            return " ".join(head.split()), state
        return None
    parts = cleaned.split()
    if len(parts) >= 2:
        state = normalize_state(parts[-1])
        if state:
            return " ".join(parts[:-1]), state
    if len(parts) >= 3:
        state = normalize_state(" ".join(parts[-2:]))
        if state:
            return " ".join(parts[:-2]), state
    return None


class Geocoder:
    def __init__(self, gazetteer=None, client=None):
        self._gazetteer = gazetteer
        self._client = client

    @property
    def gazetteer(self):
        if self._gazetteer is None:
            self._gazetteer = get_gazetteer()
        return self._gazetteer

    @property
    def client(self):
        if self._client is None:
            self._client = NominatimClient()
        return self._client

    def resolve(self, raw):
        query = " ".join((raw or "").split())
        if not query:
            raise LocationNotFound("A location is required.", query=raw)

        coordinate = parse_coordinates(query)
        if coordinate is not None:
            self._ensure_within_usa(coordinate, query)
            label = f"{coordinate.latitude:.5f}, {coordinate.longitude:.5f}"
            return ResolvedLocation(query=query, label=label, coordinate=coordinate, source="coordinates")

        place = self._lookup_gazetteer(query)
        if place is not None:
            coordinate = Coordinate(latitude=place.latitude, longitude=place.longitude)
            return ResolvedLocation(
                query=query, label=f"{place.city}, {place.state}", coordinate=coordinate, source="gazetteer"
            )

        key = query.casefold()
        entry = GeocodeCacheEntry.objects.filter(query_key=key).first()
        if entry is not None:
            coordinate = Coordinate(latitude=entry.latitude, longitude=entry.longitude)
            return ResolvedLocation(query=query, label=entry.display_name, coordinate=coordinate, source="cache")

        result = self.client.geocode(query)
        if result is None:
            raise LocationNotFound(f"Could not find a location in the USA matching '{query}'.", query=query)
        self._ensure_within_usa(result.coordinate, query)
        GeocodeCacheEntry.objects.update_or_create(
            query_key=key,
            defaults={
                "query": query,
                "display_name": result.display_name[:255],
                "latitude": result.coordinate.latitude,
                "longitude": result.coordinate.longitude,
            },
        )
        logger.info("Geocoded '%s' with Nominatim", query)
        return ResolvedLocation(
            query=query, label=result.display_name, coordinate=result.coordinate, source="nominatim"
        )

    def _lookup_gazetteer(self, query):
        parsed = split_city_state(query)
        if parsed is None:
            return None
        city, state = parsed
        return self.gazetteer.lookup(city, state)

    @staticmethod
    def _ensure_within_usa(coordinate, query):
        if not is_within_usa(coordinate):
            raise LocationOutsideUSA(
                f"'{query}' is outside the USA. Both locations must be within the USA.", query=query
            )
