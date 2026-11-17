import logging
import threading
from dataclasses import dataclass

import numpy as np
from django.db.models import Count, Max

from .models import FuelStation

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StationRecord:
    id: int
    opis_id: int
    name: str
    address: str
    city: str
    state: str
    price_per_gallon: float
    latitude: float
    longitude: float


class StationIndex:
    def __init__(self, records, signature=None):
        self.records = tuple(records)
        self.signature = signature
        self.latitudes = np.array([record.latitude for record in self.records], dtype=np.float64)
        self.longitudes = np.array([record.longitude for record in self.records], dtype=np.float64)
        self.prices = np.array([record.price_per_gallon for record in self.records], dtype=np.float64)

    def __len__(self):
        return len(self.records)

    @classmethod
    def from_database(cls):
        queryset = (
            FuelStation.objects.filter(latitude__isnull=False, longitude__isnull=False)
            .order_by("opis_id")
            .values_list("id", "opis_id", "name", "address", "city", "state", "retail_price", "latitude", "longitude")
        )
        records = [
            StationRecord(
                id=row[0],
                opis_id=row[1],
                name=row[2],
                address=row[3],
                city=row[4],
                state=row[5],
                price_per_gallon=float(row[6]),
                latitude=row[7],
                longitude=row[8],
            )
            for row in queryset
        ]
        index = cls(records, signature=database_signature())
        logger.info("Built station index with %s geocoded stations", len(index))
        return index


def database_signature():
    totals = FuelStation.objects.aggregate(total=Count("id"), latest=Max("updated_at"))
    return (totals["total"], totals["latest"])


_lock = threading.Lock()
_cached_index = None


def get_station_index():
    global _cached_index
    signature = database_signature()
    with _lock:
        if _cached_index is None or _cached_index.signature != signature:
            _cached_index = StationIndex.from_database()
        return _cached_index


def invalidate_station_index():
    global _cached_index
    with _lock:
        _cached_index = None
