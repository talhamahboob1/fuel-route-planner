from dataclasses import dataclass

import numpy as np

EPSILON = 1e-6


@dataclass(frozen=True)
class VehicleProfile:
    range_miles: float
    miles_per_gallon: float

    @property
    def tank_capacity_gallons(self):
        return self.range_miles / self.miles_per_gallon


@dataclass(frozen=True)
class RouteStation:
    station: object
    distance_from_start_miles: float
    distance_from_route_miles: float

    @property
    def price_per_gallon(self):
        return self.station.price_per_gallon


@dataclass(frozen=True)
class FuelStop:
    sequence: int
    station: object
    distance_from_start_miles: float
    distance_from_route_miles: float
    price_per_gallon: float
    gallons_purchased: float
    cost: float
    fuel_on_arrival_gallons: float
    fuel_on_departure_gallons: float


@dataclass(frozen=True)
class FuelPlan:
    stops: tuple
    starting_fuel_gallons: float
    total_cost: float
    total_gallons_purchased: float
    total_gallons_consumed: float
    fuel_at_finish_gallons: float

    @property
    def stop_count(self):
        return len(self.stops)

    @property
    def average_price_paid_per_gallon(self):
        if self.total_gallons_purchased <= 0:
            return None
        return self.total_cost / self.total_gallons_purchased


class InfeasibleTrip(Exception):
    def __init__(self, message, gap_start_miles, gap_end_miles):
        super().__init__(message)
        self.message = message
        self.gap_start_miles = gap_start_miles
        self.gap_end_miles = gap_end_miles


def prune_dominated_stations(route_stations):
    ordered = sorted(route_stations, key=lambda item: (item.distance_from_start_miles, item.price_per_gallon))
    kept = []
    for candidate in ordered:
        if kept and abs(kept[-1].distance_from_start_miles - candidate.distance_from_start_miles) < EPSILON:
            continue
        kept.append(candidate)
    return kept


def check_feasibility(stations, trip_miles, initial_range_miles, range_miles):
    position = 0.0
    available = initial_range_miles
    for station in stations:
        gap = station.distance_from_start_miles - position
        if gap > available + EPSILON:
            if position == 0.0:
                message = (
                    f"The first fuel station along the route is {gap:.0f} miles from the start, "
                    f"but the starting fuel only covers {available:.0f} miles."
                )
            else:
                message = (
                    f"There is a {gap:.0f} mile stretch between mile {position:.0f} and mile "
                    f"{station.distance_from_start_miles:.0f} with no known fuel station, which exceeds "
                    f"the vehicle range of {range_miles:.0f} miles."
                )
            raise InfeasibleTrip(message, position, station.distance_from_start_miles)
        position = station.distance_from_start_miles
        available = range_miles
    gap = trip_miles - position
    if gap > available + EPSILON:
        if not stations:
            message = (
                f"No fuel station was found along the {trip_miles:.0f} mile route and the starting fuel "
                f"only covers {available:.0f} miles."
            )
        else:
            message = (
                f"The last known fuel station is {gap:.0f} miles before the finish, which exceeds "
                f"the vehicle range of {range_miles:.0f} miles."
            )
        raise InfeasibleTrip(message, position, trip_miles)


def plan_fuel_stops(
    route_stations,
    trip_miles,
    vehicle,
    starting_fuel_gallons=None,
    min_purchase_gallons=0.0,
    min_price_drop_per_gallon=0.0,
):
    capacity = vehicle.tank_capacity_gallons
    mpg = vehicle.miles_per_gallon
    if starting_fuel_gallons is None:
        fuel = capacity
    else:
        fuel = min(max(float(starting_fuel_gallons), 0.0), capacity)
    starting_fuel = fuel

    stations = prune_dominated_stations(route_stations)
    check_feasibility(stations, trip_miles, fuel * mpg, vehicle.range_miles)

    positions = np.array([station.distance_from_start_miles for station in stations], dtype=np.float64)
    prices = np.array([station.price_per_gallon for station in stations], dtype=np.float64)

    stops = []
    position = 0.0
    for index, current in enumerate(stations):
        fuel = max(fuel - (current.distance_from_start_miles - position) / mpg, 0.0)
        position = current.distance_from_start_miles
        arrival = fuel

        purchase = float(
            _purchase_amount(index, positions, prices, trip_miles, vehicle, fuel, min_price_drop_per_gallon)
        )
        if 0.0 < purchase < min_purchase_gallons:
            next_position = float(positions[index + 1]) if index + 1 < len(stations) else trip_miles
            if fuel * mpg + EPSILON >= next_position - position:
                purchase = 0.0
            else:
                purchase = min(min_purchase_gallons, capacity - fuel)

        if purchase > EPSILON:
            fuel += purchase
            gallons = round(purchase, 2)
            stops.append(
                FuelStop(
                    sequence=len(stops) + 1,
                    station=current.station,
                    distance_from_start_miles=current.distance_from_start_miles,
                    distance_from_route_miles=current.distance_from_route_miles,
                    price_per_gallon=current.price_per_gallon,
                    gallons_purchased=gallons,
                    cost=round(gallons * current.price_per_gallon, 2),
                    fuel_on_arrival_gallons=arrival,
                    fuel_on_departure_gallons=fuel,
                )
            )

    fuel = max(fuel - (trip_miles - position) / mpg, 0.0)
    total_purchased = round(sum(stop.gallons_purchased for stop in stops), 2)
    return FuelPlan(
        stops=tuple(stops),
        starting_fuel_gallons=starting_fuel,
        total_cost=round(sum(stop.cost for stop in stops), 2),
        total_gallons_purchased=total_purchased,
        total_gallons_consumed=trip_miles / mpg,
        fuel_at_finish_gallons=fuel,
    )


def _purchase_amount(index, positions, prices, trip_miles, vehicle, fuel, min_price_drop):
    capacity = vehicle.tank_capacity_gallons
    mpg = vehicle.miles_per_gallon
    current_position = positions[index]
    current_price = prices[index]
    reach = current_position + vehicle.range_miles
    finish_in_reach = trip_miles <= reach + EPSILON
    window_end = int(np.searchsorted(positions, reach + EPSILON, side="right"))
    window_prices = prices[index + 1 : window_end]
    cheaper = np.flatnonzero(window_prices < current_price - EPSILON)

    coverable = current_position + fuel * mpg
    if len(cheaper) and positions[index + 1 + cheaper[0]] <= coverable + EPSILON:
        return 0.0
    if len(cheaper) == 0:
        if finish_in_reach:
            return max(0.0, (trip_miles - current_position) / mpg - fuel)
        return max(0.0, capacity - fuel)

    worthwhile = cheaper[window_prices[cheaper] <= current_price - min_price_drop + EPSILON]
    if len(worthwhile):
        target = positions[index + 1 + worthwhile[0]]
    elif finish_in_reach:
        target = trip_miles
    else:
        target = positions[index + 1 + cheaper[np.argmin(window_prices[cheaper])]]
    return max(0.0, (target - current_position) / mpg - fuel)
