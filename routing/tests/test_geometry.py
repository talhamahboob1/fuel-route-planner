import numpy as np
from django.test import SimpleTestCase

from routing.geometry import (
    bounding_box,
    cumulative_distances_miles,
    haversine_miles,
    nearest_route_points,
    resample_route,
    simplify_coordinates,
)
from routing.types import Coordinate


class GeometryTests(SimpleTestCase):
    def test_haversine_for_one_degree_of_latitude(self):
        self.assertAlmostEqual(float(haversine_miles(35.0, -97.0, 36.0, -97.0)), 69.09, places=1)

    def test_cumulative_distances_start_at_zero(self):
        distances = cumulative_distances_miles([35.0, 36.0, 37.0], [-97.0, -97.0, -97.0])
        self.assertEqual(distances[0], 0.0)
        self.assertAlmostEqual(distances[2], 138.18, places=1)

    def test_resampling_uses_requested_spacing_and_total(self):
        lats, lons, distances = resample_route([35.0, 36.0], [-97.0, -97.0], spacing_miles=10.0, total_miles=70.0)

        self.assertEqual(distances[0], 0.0)
        self.assertEqual(distances[-1], 70.0)
        self.assertEqual(len(distances), 8)
        self.assertAlmostEqual(lats[-1], 36.0)
        self.assertTrue(np.all(lons == -97.0))

    def test_nearest_route_point_distance(self):
        route_lats = np.linspace(35.0, 36.0, 101)
        route_lons = np.full(101, -97.0)
        point_lat = 35.5
        point_lon = -97.0 + 1.0 / (69.09 * np.cos(np.radians(35.5)))

        indices, distances = nearest_route_points(route_lats, route_lons, [point_lat], [point_lon])

        self.assertEqual(indices[0], 50)
        self.assertAlmostEqual(distances[0], 1.0, places=1)

    def test_simplification_keeps_corners_and_drops_collinear_points(self):
        line = [Coordinate(35.0 + i * 0.01, -97.0) for i in range(11)]
        line += [Coordinate(35.1, -97.0 - i * 0.01) for i in range(1, 11)]

        simplified = simplify_coordinates(line, tolerance_meters=30.0)

        self.assertEqual(simplified, [line[0], line[10], line[-1]])

    def test_bounding_box(self):
        box = bounding_box([Coordinate(35.0, -97.0), Coordinate(36.0, -95.0)])
        self.assertEqual(box, {"south": 35.0, "west": -97.0, "north": 36.0, "east": -95.0})
