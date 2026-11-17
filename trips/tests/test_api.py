from decimal import Decimal
from unittest import mock

import numpy as np
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from routing.clients.osrm import OSRMClient
from routing.exceptions import ExternalServiceError, RouteNotFound
from routing.types import METERS_PER_MILE, Coordinate, Route
from stations.index import invalidate_station_index
from stations.models import FuelStation

START = "35.0,-100.0"
FINISH = "35.0,-90.0"


def synthetic_route(points=201):
    lons = np.linspace(-100.0, -90.0, points)
    coordinates = tuple(Coordinate(35.0, float(lon)) for lon in lons)
    miles = 10.0 * 69.09 * np.cos(np.radians(35.0))
    return Route(distance_meters=miles * METERS_PER_MILE, duration_seconds=9.5 * 3600, coordinates=coordinates)


def create_station(opis_id, longitude, price, latitude=35.01):
    return FuelStation.objects.create(
        opis_id=opis_id,
        name=f"Truck Stop {opis_id}",
        address="I-40, EXIT 1",
        city="Town",
        state="OK",
        rack_id=1,
        retail_price=Decimal(str(price)),
        latitude=latitude,
        longitude=longitude,
    )


class TripPlanAPITests(TestCase):
    def setUp(self):
        cache.clear()
        invalidate_station_index()
        self.url = reverse("route-plan")
        patcher = mock.patch.object(OSRMClient, "route", return_value=synthetic_route())
        self.route_mock = patcher.start()
        self.addCleanup(patcher.stop)
        create_station(1, -99.0, "3.50")
        create_station(2, -97.0, "2.90")
        create_station(3, -93.0, "3.30")

    def test_get_returns_a_plan_with_stops_and_totals(self):
        response = self.client.get(self.url, {"start": START, "finish": FINISH})

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload["start"]["resolved_by"], "coordinates")
        self.assertAlmostEqual(payload["route"]["distance_miles"], 566.0, delta=1.0)
        self.assertEqual(payload["route"]["geometry"]["type"], "LineString")
        self.assertEqual(
            payload["vehicle"],
            {
                "range_miles": 500.0,
                "miles_per_gallon": 10.0,
                "tank_capacity_gallons": 50.0,
                "starting_fuel_gallons": 50.0,
            },
        )
        self.assertEqual(payload["external_api_calls"], {"routing": 1, "geocoding": 0})
        self.assertFalse(payload["cached"])
        self.assertEqual(payload["stations_considered"], 3)
        self.assertEqual(
            payload["policy"],
            {
                "max_detour_miles": 10.0,
                "min_purchase_gallons": 5.0,
                "min_price_drop_per_gallon": 0.1,
            },
        )

        stops = payload["fuel_stops"]
        self.assertEqual([stop["station"]["opis_id"] for stop in stops], [2])
        self.assertEqual(stops[0]["sequence"], 1)
        self.assertAlmostEqual(stops[0]["price_per_gallon"], 2.9)
        self.assertAlmostEqual(stops[0]["gallons_purchased"], 6.6, delta=0.2)
        self.assertAlmostEqual(payload["summary"]["total_fuel_cost"], stops[0]["cost"])
        self.assertEqual(payload["summary"]["fuel_stop_count"], 1)
        self.assertEqual(payload["summary"]["currency"], "USD")
        self.assertIn("start=35.0%2C-100.0", payload["map_url"])

    def test_repeated_requests_are_served_from_cache(self):
        self.client.get(self.url, {"start": START, "finish": FINISH})
        response = self.client.get(self.url, {"start": START, "finish": FINISH})

        self.assertTrue(response.json()["cached"])
        self.assertEqual(self.route_mock.call_count, 1)

    def test_post_with_json_body(self):
        response = self.client.post(
            self.url,
            {"start": START, "finish": FINISH, "starting_fuel_gallons": 10, "include_geometry": False},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertIsNone(payload["route"]["geometry"])
        self.assertEqual(payload["vehicle"]["starting_fuel_gallons"], 10.0)
        self.assertEqual([stop["station"]["opis_id"] for stop in payload["fuel_stops"]], [1, 2])
        self.assertIn("starting_fuel_gallons=10", payload["map_url"])

    def test_missing_parameters_are_rejected(self):
        response = self.client.get(self.url, {"start": START})

        self.assertEqual(response.status_code, 400)
        error = response.json()["error"]
        self.assertEqual(error["code"], "validation_error")
        self.assertIn("finish", error["details"])

    def test_starting_fuel_above_capacity_is_rejected(self):
        response = self.client.get(self.url, {"start": START, "finish": FINISH, "starting_fuel_gallons": 80})

        self.assertEqual(response.status_code, 400)
        self.assertIn("starting_fuel_gallons", response.json()["error"]["details"])

    def test_location_outside_usa_is_rejected(self):
        response = self.client.get(self.url, {"start": "48.85,2.35", "finish": FINISH})

        self.assertEqual(response.status_code, 400)
        error = response.json()["error"]
        self.assertEqual(error["code"], "location_not_found")
        self.assertEqual(error["details"]["field"], "start")

    def test_route_not_found_maps_to_422(self):
        self.route_mock.side_effect = RouteNotFound("No drivable route was found between the two locations.")

        response = self.client.get(self.url, {"start": START, "finish": FINISH})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "route_not_found")

    def test_upstream_failure_maps_to_503(self):
        self.route_mock.side_effect = ExternalServiceError("routing", "The routing service could not be reached.")

        response = self.client.get(self.url, {"start": START, "finish": FINISH})

        self.assertEqual(response.status_code, 503)
        error = response.json()["error"]
        self.assertEqual(error["code"], "upstream_unavailable")
        self.assertEqual(error["details"]["service"], "routing")

    def test_infeasible_trip_maps_to_422(self):
        FuelStation.objects.all().delete()
        invalidate_station_index()

        response = self.client.get(self.url, {"start": START, "finish": FINISH})

        self.assertEqual(response.status_code, 422)
        error = response.json()["error"]
        self.assertEqual(error["code"], "trip_not_feasible")
        self.assertEqual(error["details"]["gap_start_miles"], 0.0)

    def test_health_endpoint_reports_station_counts(self):
        response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "stations_loaded": 3, "stations_geocoded": 3})

    def test_map_page_renders(self):
        response = self.client.get(reverse("map"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fuel Route Planner")

    def test_openapi_schema_is_generated(self):
        response = self.client.get(reverse("schema"))

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"/api/v1/route/", response.content)
