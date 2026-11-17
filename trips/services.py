import hashlib
import json
import logging
from dataclasses import dataclass, replace

from django.conf import settings
from django.core.cache import cache

from routing.clients.osrm import OSRMClient
from routing.exceptions import LocationNotFound
from routing.geocoding import Geocoder
from routing.geometry import simplify_coordinates
from stations.index import get_station_index

from .candidates import find_stations_along_route
from .planner import VehicleProfile, plan_fuel_stops

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TripPlanRequest:
    start: str
    finish: str
    starting_fuel_gallons: float = None
    max_detour_miles: float = None


@dataclass(frozen=True)
class PlanningPolicy:
    max_detour_miles: float
    min_purchase_gallons: float
    min_price_drop_per_gallon: float


@dataclass(frozen=True)
class TripPlan:
    start: object
    finish: object
    vehicle: VehicleProfile
    distance_miles: float
    duration_seconds: float
    geometry: list
    fuel_plan: object
    stations_considered: int
    policy: PlanningPolicy
    external_api_calls: dict
    cached: bool = False


def vehicle_from_settings():
    config = settings.FUEL_ROUTER
    return VehicleProfile(
        range_miles=float(config["VEHICLE_RANGE_MILES"]),
        miles_per_gallon=float(config["VEHICLE_MILES_PER_GALLON"]),
    )


class TripPlanner:
    def __init__(self, geocoder=None, routing_client=None, station_index_provider=get_station_index):
        self.geocoder = geocoder or Geocoder()
        self.routing_client = routing_client or OSRMClient()
        self.station_index_provider = station_index_provider

    def plan(self, request):
        config = settings.FUEL_ROUTER
        vehicle = vehicle_from_settings()
        policy = PlanningPolicy(
            max_detour_miles=request.max_detour_miles or float(config["MAX_DETOUR_MILES"]),
            min_purchase_gallons=float(config["MIN_PURCHASE_GALLONS"]),
            min_price_drop_per_gallon=float(config["MIN_PRICE_DROP_PER_GALLON"]),
        )

        cache_key = self._cache_key(request, vehicle, policy)
        cached = cache.get(cache_key)
        if cached is not None:
            return replace(cached, cached=True)

        start = self._resolve(request.start, "start")
        finish = self._resolve(request.finish, "finish")
        route = self.routing_client.route(start.coordinate, finish.coordinate)
        logger.info(
            "Routed %s to %s: %.1f miles in %.0f minutes with %s geometry points",
            start.label,
            finish.label,
            route.distance_miles,
            route.duration_minutes,
            len(route.coordinates),
        )

        candidates = find_stations_along_route(
            route,
            self.station_index_provider(),
            policy.max_detour_miles,
            float(config["ROUTE_SAMPLE_SPACING_MILES"]),
        )
        fuel_plan = plan_fuel_stops(
            candidates,
            route.distance_miles,
            vehicle,
            starting_fuel_gallons=request.starting_fuel_gallons,
            min_purchase_gallons=policy.min_purchase_gallons,
            min_price_drop_per_gallon=policy.min_price_drop_per_gallon,
        )
        geometry = simplify_coordinates(route.coordinates, float(config["ROUTE_GEOMETRY_TOLERANCE_METERS"]))

        plan = TripPlan(
            start=start,
            finish=finish,
            vehicle=vehicle,
            distance_miles=route.distance_miles,
            duration_seconds=route.duration_seconds,
            geometry=geometry,
            fuel_plan=fuel_plan,
            stations_considered=len(candidates),
            policy=policy,
            external_api_calls={
                "routing": 1,
                "geocoding": sum(1 for location in (start, finish) if location.source == "nominatim"),
            },
        )
        cache.set(cache_key, plan, int(config["RESULT_CACHE_SECONDS"]))
        return plan

    def _resolve(self, raw, field):
        try:
            return self.geocoder.resolve(raw)
        except LocationNotFound as exc:
            exc.field = field
            raise

    @staticmethod
    def _cache_key(request, vehicle, policy):
        payload = json.dumps(
            {
                "start": " ".join(request.start.split()).casefold(),
                "finish": " ".join(request.finish.split()).casefold(),
                "starting_fuel": request.starting_fuel_gallons,
                "policy": [policy.max_detour_miles, policy.min_purchase_gallons, policy.min_price_drop_per_gallon],
                "range": vehicle.range_miles,
                "mpg": vehicle.miles_per_gallon,
            },
            sort_keys=True,
        )
        return "trip-plan:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
