import numpy as np
from django.test import SimpleTestCase

from routing.types import METERS_PER_MILE, Coordinate, Route
from stations.index import StationIndex, StationRecord
from trips.candidates import find_stations_along_route


def record(opis_id, latitude, longitude, price=3.0):
    return StationRecord(opis_id, opis_id, f"Stop {opis_id}", "I-40", "Town", "OK", price, latitude, longitude)


def straight_route(points=51):
    lons = np.linspace(-100.0, -95.0, points)
    coordinates = tuple(Coordinate(35.0, float(lon)) for lon in lons)
    miles = 5.0 * 69.09 * np.cos(np.radians(35.0))
    return Route(distance_meters=miles * METERS_PER_MILE, duration_seconds=3600.0, coordinates=coordinates)


class CandidateSearchTests(SimpleTestCase):
    def test_stations_near_the_route_are_positioned_along_it(self):
        route = straight_route()
        near_mid = record(1, 35.02, -97.5)
        far_away = record(2, 36.5, -97.5)
        near_start = record(3, 35.0, -99.9)
        index = StationIndex([near_mid, far_away, near_start])

        found = find_stations_along_route(route, index, max_detour_miles=10.0, spacing_miles=0.5)

        self.assertEqual([item.station.opis_id for item in found], [3, 1])
        self.assertLess(found[0].distance_from_start_miles, 8.0)
        self.assertAlmostEqual(found[1].distance_from_start_miles, route.distance_miles / 2, delta=3.0)
        self.assertAlmostEqual(found[1].distance_from_route_miles, 1.4, delta=0.2)

    def test_empty_index_returns_nothing(self):
        self.assertEqual(find_stations_along_route(straight_route(), StationIndex([]), 10.0, 0.5), [])
