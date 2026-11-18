from django.test import SimpleTestCase

from stations.index import StationRecord
from trips.planner import InfeasibleTrip, RouteStation, VehicleProfile, plan_fuel_stops

VEHICLE = VehicleProfile(range_miles=500.0, miles_per_gallon=10.0)


def station(opis_id, mile, price, detour=0.5):
    record = StationRecord(
        id=opis_id,
        opis_id=opis_id,
        name=f"Stop {opis_id}",
        address="I-40",
        city="Town",
        state="OK",
        price_per_gallon=price,
        latitude=35.0,
        longitude=-97.0,
    )
    return RouteStation(station=record, distance_from_start_miles=mile, distance_from_route_miles=detour)


class PlannerTests(SimpleTestCase):
    def test_short_trip_on_a_full_tank_needs_no_stops(self):
        plan = plan_fuel_stops([station(1, 100, 3.0)], 300.0, VEHICLE)

        self.assertEqual(plan.stops, ())
        self.assertEqual(plan.total_cost, 0.0)
        self.assertAlmostEqual(plan.fuel_at_finish_gallons, 20.0)
        self.assertAlmostEqual(plan.total_gallons_consumed, 30.0)
        self.assertIsNone(plan.average_price_paid_per_gallon)

    def test_fills_up_at_cheap_station_and_tops_up_at_expensive_one(self):
        stations = [station(1, 400, 3.0), station(2, 800, 4.0)]

        plan = plan_fuel_stops(stations, 1000.0, VEHICLE)

        self.assertEqual([stop.station.opis_id for stop in plan.stops], [1, 2])
        self.assertAlmostEqual(plan.stops[0].gallons_purchased, 40.0)
        self.assertAlmostEqual(plan.stops[0].cost, 120.0)
        self.assertAlmostEqual(plan.stops[0].fuel_on_arrival_gallons, 10.0)
        self.assertAlmostEqual(plan.stops[0].fuel_on_departure_gallons, 50.0)
        self.assertAlmostEqual(plan.stops[1].gallons_purchased, 10.0)
        self.assertAlmostEqual(plan.stops[1].cost, 40.0)
        self.assertAlmostEqual(plan.total_cost, 160.0)
        self.assertAlmostEqual(plan.total_gallons_purchased, 50.0)
        self.assertAlmostEqual(plan.fuel_at_finish_gallons, 0.0)
        self.assertAlmostEqual(plan.average_price_paid_per_gallon, 3.2)

    def test_buys_only_enough_to_reach_a_cheaper_station(self):
        stations = [station(1, 100, 4.0), station(2, 300, 3.0)]

        plan = plan_fuel_stops(stations, 600.0, VEHICLE, starting_fuel_gallons=20.0)

        self.assertEqual(len(plan.stops), 2)
        self.assertAlmostEqual(plan.stops[0].gallons_purchased, 10.0)
        self.assertAlmostEqual(plan.stops[1].gallons_purchased, 30.0)
        self.assertAlmostEqual(plan.total_cost, 130.0)
        self.assertAlmostEqual(plan.starting_fuel_gallons, 20.0)

    def test_skips_expensive_station_when_cheaper_one_is_reachable(self):
        stations = [station(1, 100, 4.5), station(2, 450, 2.5)]

        plan = plan_fuel_stops(stations, 900.0, VEHICLE)

        self.assertEqual([stop.station.opis_id for stop in plan.stops], [2])
        self.assertAlmostEqual(plan.stops[0].fuel_on_arrival_gallons, 5.0)
        self.assertAlmostEqual(plan.stops[0].gallons_purchased, 40.0)
        self.assertAlmostEqual(plan.fuel_at_finish_gallons, 0.0)

    def test_gap_longer_than_range_is_infeasible(self):
        stations = [station(1, 100, 3.0), station(2, 700, 3.0)]

        with self.assertRaises(InfeasibleTrip) as raised:
            plan_fuel_stops(stations, 900.0, VEHICLE)

        self.assertEqual(raised.exception.gap_start_miles, 100.0)
        self.assertEqual(raised.exception.gap_end_miles, 700.0)
        self.assertIn("600 mile stretch", raised.exception.message)

    def test_starting_fuel_must_reach_the_first_station(self):
        with self.assertRaises(InfeasibleTrip) as raised:
            plan_fuel_stops([station(1, 200, 3.0)], 400.0, VEHICLE, starting_fuel_gallons=10.0)

        self.assertEqual(raised.exception.gap_start_miles, 0.0)
        self.assertIn("starting fuel only covers 100 miles", raised.exception.message)

    def test_no_stations_and_trip_beyond_range_is_infeasible(self):
        with self.assertRaises(InfeasibleTrip):
            plan_fuel_stops([], 600.0, VEHICLE)

    def test_tiny_optional_purchases_are_skipped(self):
        stations = [station(1, 10, 2.0), station(2, 480, 3.0)]

        exact = plan_fuel_stops(stations, 900.0, VEHICLE, min_purchase_gallons=0.0)
        practical = plan_fuel_stops(stations, 900.0, VEHICLE, min_purchase_gallons=5.0)

        self.assertEqual(len(exact.stops), 2)
        self.assertAlmostEqual(exact.stops[0].gallons_purchased, 1.0)
        self.assertEqual(len(practical.stops), 1)
        self.assertEqual(practical.stops[0].station.opis_id, 2)
        self.assertAlmostEqual(practical.stops[0].gallons_purchased, 40.0)

    def test_required_small_purchases_are_raised_to_the_minimum(self):
        plan = plan_fuel_stops([station(1, 450, 3.0)], 520.0, VEHICLE, min_purchase_gallons=5.0)

        self.assertEqual(len(plan.stops), 1)
        self.assertAlmostEqual(plan.stops[0].gallons_purchased, 5.0)
        self.assertAlmostEqual(plan.fuel_at_finish_gallons, 3.0)

    def test_cheapest_station_wins_at_the_same_position(self):
        stations = [station(1, 400, 3.5), station(2, 400, 3.0), station(3, 400, 3.2)]

        plan = plan_fuel_stops(stations, 800.0, VEHICLE)

        self.assertEqual([stop.station.opis_id for stop in plan.stops], [2])

    def test_never_exceeds_tank_capacity(self):
        stations = [
            station(index, mile, 3.0 + (index % 3) * 0.2) for index, mile in enumerate(range(50, 2000, 50), start=1)
        ]

        plan = plan_fuel_stops(stations, 2000.0, VEHICLE)

        for stop in plan.stops:
            self.assertLessEqual(stop.fuel_on_departure_gallons, 50.0 + 1e-6)
            self.assertGreater(stop.gallons_purchased, 0)
        self.assertAlmostEqual(plan.total_gallons_purchased, sum(s.gallons_purchased for s in plan.stops), places=2)
        self.assertGreaterEqual(plan.total_gallons_purchased, 150.0 - 1e-6)

    def test_marginal_price_drops_are_consolidated_into_one_purchase(self):
        stations = [station(1, 100, 3.00), station(2, 200, 2.98), station(3, 300, 2.96), station(4, 400, 2.80)]

        exact = plan_fuel_stops(stations, 900.0, VEHICLE, starting_fuel_gallons=10.0)
        practical = plan_fuel_stops(
            stations, 900.0, VEHICLE, starting_fuel_gallons=10.0, min_price_drop_per_gallon=0.10
        )

        self.assertEqual([stop.station.opis_id for stop in exact.stops], [1, 2, 3, 4])
        self.assertEqual([stop.station.opis_id for stop in practical.stops], [1, 4])
        self.assertAlmostEqual(practical.stops[0].gallons_purchased, 30.0)
        self.assertAlmostEqual(practical.stops[1].gallons_purchased, 50.0)
        self.assertAlmostEqual(exact.total_cost, 229.4)
        self.assertAlmostEqual(practical.total_cost, 230.0)

    def test_marginally_cheaper_station_before_finish_is_skipped(self):
        stations = [station(1, 100, 3.00), station(2, 300, 2.95)]

        plan = plan_fuel_stops(stations, 500.0, VEHICLE, starting_fuel_gallons=10.0, min_price_drop_per_gallon=0.10)

        self.assertEqual([stop.station.opis_id for stop in plan.stops], [1])
        self.assertAlmostEqual(plan.stops[0].gallons_purchased, 40.0)
        self.assertAlmostEqual(plan.fuel_at_finish_gallons, 0.0)

    def test_defers_buying_when_a_cheaper_station_is_already_reachable(self):
        stations = [station(1, 10, 3.20), station(2, 12, 3.15), station(3, 300, 3.00)]

        plan = plan_fuel_stops(stations, 400.0, VEHICLE, starting_fuel_gallons=10.0, min_price_drop_per_gallon=0.10)

        self.assertEqual([stop.station.opis_id for stop in plan.stops], [2, 3])
        self.assertAlmostEqual(plan.stops[0].gallons_purchased, 20.0)
        self.assertAlmostEqual(plan.stops[1].gallons_purchased, 10.0)
        self.assertAlmostEqual(plan.total_cost, 93.0)

    def test_zero_threshold_reproduces_exact_greedy(self):
        stations = [station(1, 100, 3.00), station(2, 300, 2.95)]

        plan = plan_fuel_stops(stations, 500.0, VEHICLE, starting_fuel_gallons=10.0, min_price_drop_per_gallon=0.0)

        self.assertEqual([stop.station.opis_id for stop in plan.stops], [1, 2])
        self.assertAlmostEqual(plan.stops[0].gallons_purchased, 20.0)
        self.assertAlmostEqual(plan.stops[1].gallons_purchased, 20.0)

    def test_starting_fuel_above_capacity_is_clamped(self):
        plan = plan_fuel_stops([], 100.0, VEHICLE, starting_fuel_gallons=80.0)
        self.assertAlmostEqual(plan.starting_fuel_gallons, 50.0)
