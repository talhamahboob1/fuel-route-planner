from decimal import Decimal

from django.test import TestCase

from stations.index import get_station_index, invalidate_station_index
from stations.models import FuelStation


def create_station(opis_id, price, latitude=35.0, longitude=-97.0):
    return FuelStation.objects.create(
        opis_id=opis_id,
        name=f"Station {opis_id}",
        address="I-40",
        city="Town",
        state="OK",
        rack_id=1,
        retail_price=Decimal(str(price)),
        latitude=latitude,
        longitude=longitude,
    )


class StationIndexTests(TestCase):
    def setUp(self):
        invalidate_station_index()

    def test_index_only_contains_geocoded_stations(self):
        create_station(1, "3.10")
        create_station(2, "3.20", latitude=None, longitude=None)

        index = get_station_index()

        self.assertEqual(len(index), 1)
        self.assertEqual(index.records[0].opis_id, 1)
        self.assertAlmostEqual(index.prices[0], 3.10)
        self.assertAlmostEqual(index.latitudes[0], 35.0)

    def test_index_refreshes_when_stations_change(self):
        create_station(1, "3.10")
        first = get_station_index()
        self.assertIs(get_station_index(), first)

        create_station(2, "3.30")

        second = get_station_index()
        self.assertIsNot(second, first)
        self.assertEqual(len(second), 2)
