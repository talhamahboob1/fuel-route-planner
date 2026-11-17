from dataclasses import dataclass
from typing import NamedTuple

METERS_PER_MILE = 1609.344


class Coordinate(NamedTuple):
    latitude: float
    longitude: float


@dataclass(frozen=True)
class Route:
    distance_meters: float
    duration_seconds: float
    coordinates: tuple

    @property
    def distance_miles(self):
        return self.distance_meters / METERS_PER_MILE

    @property
    def duration_minutes(self):
        return self.duration_seconds / 60.0
