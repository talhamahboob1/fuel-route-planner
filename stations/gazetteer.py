import csv
import logging
import re
from dataclasses import dataclass
from functools import lru_cache

from django.conf import settings

logger = logging.getLogger(__name__)

NON_ALPHANUMERIC = re.compile(r"[^A-Z0-9 ]+")
LEADING_ABBREVIATIONS = (
    ("ST ", "SAINT "),
    ("STE ", "SAINTE "),
    ("MT ", "MOUNT "),
    ("FT ", "FORT "),
    ("N ", "NORTH "),
    ("S ", "SOUTH "),
    ("E ", "EAST "),
    ("W ", "WEST "),
)


def normalize_city_name(name):
    cleaned = NON_ALPHANUMERIC.sub(" ", name.upper())
    cleaned = " ".join(cleaned.split())
    for short, full in LEADING_ABBREVIATIONS:
        if cleaned.startswith(short):
            cleaned = full + cleaned[len(short) :]
            break
    return cleaned


def compact_city_name(name):
    return normalize_city_name(name).replace(" ", "")


@dataclass(frozen=True)
class Place:
    city: str
    state: str
    latitude: float
    longitude: float
    postal_codes: int = 1


class Gazetteer:
    def __init__(self, places):
        self._exact = {}
        self._compact = {}
        for place in places:
            self._register(self._exact, (normalize_city_name(place.city), place.state), place)
            self._register(self._compact, (compact_city_name(place.city), place.state), place)

    @staticmethod
    def _register(table, key, place):
        existing = table.get(key)
        if existing is None or place.postal_codes > existing.postal_codes:
            table[key] = place

    @classmethod
    def from_csv(cls, path):
        places = []
        with open(path, newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                places.append(
                    Place(
                        city=row["city"],
                        state=row["state"].upper(),
                        latitude=float(row["latitude"]),
                        longitude=float(row["longitude"]),
                        postal_codes=int(row.get("postal_codes") or 1),
                    )
                )
        logger.info("Loaded %s places from gazetteer %s", len(places), path)
        return cls(places)

    def lookup(self, city, state):
        if not city or not state:
            return None
        state = state.strip().upper()
        place = self._exact.get((normalize_city_name(city), state))
        if place is None:
            place = self._compact.get((compact_city_name(city), state))
        return place

    def __len__(self):
        return len(self._exact)


@lru_cache(maxsize=1)
def get_gazetteer():
    return Gazetteer.from_csv(settings.FUEL_ROUTER["GAZETTEER_PATH"])
