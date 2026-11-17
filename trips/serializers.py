from urllib.parse import urlencode

from django.conf import settings
from django.urls import reverse
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from routing.geometry import bounding_box

from .services import vehicle_from_settings


class RoundedFloatField(serializers.FloatField):
    def __init__(self, decimals=2, **kwargs):
        self.decimals = decimals
        super().__init__(**kwargs)

    def to_representation(self, value):
        if value is None:
            return None
        return round(float(value), self.decimals)


class TripPlanRequestSerializer(serializers.Serializer):
    start = serializers.CharField(
        max_length=200,
        help_text="Start location inside the USA: 'City, ST', a street address, or 'latitude,longitude'.",
    )
    finish = serializers.CharField(
        max_length=200,
        help_text="Finish location inside the USA, in the same formats as start.",
    )
    starting_fuel_gallons = serializers.FloatField(
        required=False,
        min_value=0.0,
        help_text="Fuel in the tank when the trip begins. Defaults to a full tank.",
    )
    max_detour_miles = serializers.FloatField(
        required=False,
        min_value=0.5,
        help_text=(
            "How far off the route a station may be to count as along the route. Defaults to the server setting."
        ),
    )
    include_geometry = serializers.BooleanField(
        required=False,
        default=True,
        help_text="Set to false to omit the route geometry from the response.",
    )

    def validate_starting_fuel_gallons(self, value):
        capacity = vehicle_from_settings().tank_capacity_gallons
        if value > capacity + 1e-9:
            raise serializers.ValidationError(f"Cannot exceed the tank capacity of {capacity:g} gallons.")
        return value

    def validate_max_detour_miles(self, value):
        limit = float(settings.FUEL_ROUTER["MAX_DETOUR_MILES_LIMIT"])
        if value > limit:
            raise serializers.ValidationError(f"Cannot exceed {limit:g} miles.")
        return value


class LocationSerializer(serializers.Serializer):
    query = serializers.CharField()
    label = serializers.CharField()
    latitude = RoundedFloatField(decimals=6, source="coordinate.latitude")
    longitude = RoundedFloatField(decimals=6, source="coordinate.longitude")
    resolved_by = serializers.CharField(source="source")


class VehicleSerializer(serializers.Serializer):
    range_miles = RoundedFloatField(decimals=1, source="vehicle.range_miles")
    miles_per_gallon = RoundedFloatField(decimals=2, source="vehicle.miles_per_gallon")
    tank_capacity_gallons = RoundedFloatField(decimals=2, source="vehicle.tank_capacity_gallons")
    starting_fuel_gallons = RoundedFloatField(decimals=2, source="fuel_plan.starting_fuel_gallons")


class StationSerializer(serializers.Serializer):
    opis_id = serializers.IntegerField()
    name = serializers.CharField()
    address = serializers.CharField()
    city = serializers.CharField()
    state = serializers.CharField()
    latitude = RoundedFloatField(decimals=6)
    longitude = RoundedFloatField(decimals=6)


class FuelStopSerializer(serializers.Serializer):
    sequence = serializers.IntegerField()
    station = StationSerializer()
    distance_from_start_miles = RoundedFloatField(decimals=1)
    distance_from_route_miles = RoundedFloatField(decimals=1)
    price_per_gallon = RoundedFloatField(decimals=3)
    gallons_purchased = RoundedFloatField(decimals=2)
    cost = RoundedFloatField(decimals=2)
    fuel_on_arrival_gallons = RoundedFloatField(decimals=2)
    fuel_on_departure_gallons = RoundedFloatField(decimals=2)


class RouteSerializer(serializers.Serializer):
    distance_miles = RoundedFloatField(decimals=1)
    duration_minutes = serializers.SerializerMethodField()
    duration_text = serializers.SerializerMethodField()
    bounding_box = serializers.SerializerMethodField()
    geometry = serializers.SerializerMethodField()

    @extend_schema_field(serializers.IntegerField())
    def get_duration_minutes(self, plan):
        return int(round(plan.duration_seconds / 60.0))

    @extend_schema_field(serializers.CharField())
    def get_duration_text(self, plan):
        minutes = int(round(plan.duration_seconds / 60.0))
        hours, minutes = divmod(minutes, 60)
        return f"{hours}h {minutes:02d}m"

    @extend_schema_field(serializers.DictField(child=serializers.FloatField()))
    def get_bounding_box(self, plan):
        box = bounding_box(plan.geometry)
        if box is None:
            return None
        return {key: round(value, 6) for key, value in box.items()}

    @extend_schema_field(serializers.DictField())
    def get_geometry(self, plan):
        if not self.context.get("include_geometry", True):
            return None
        return {
            "type": "LineString",
            "coordinates": [[round(point.longitude, 5), round(point.latitude, 5)] for point in plan.geometry],
        }


class SummarySerializer(serializers.Serializer):
    total_fuel_cost = RoundedFloatField(decimals=2, source="total_cost")
    total_gallons_purchased = RoundedFloatField(decimals=2)
    total_gallons_consumed = RoundedFloatField(decimals=2)
    fuel_stop_count = serializers.IntegerField(source="stop_count")
    average_price_paid_per_gallon = RoundedFloatField(decimals=3, allow_null=True)
    fuel_at_finish_gallons = RoundedFloatField(decimals=2)
    currency = serializers.SerializerMethodField()

    @extend_schema_field(serializers.CharField())
    def get_currency(self, plan):
        return "USD"


class PolicySerializer(serializers.Serializer):
    max_detour_miles = RoundedFloatField(decimals=1)
    min_purchase_gallons = RoundedFloatField(decimals=2)
    min_price_drop_per_gallon = RoundedFloatField(decimals=3)


class TripPlanSerializer(serializers.Serializer):
    start = LocationSerializer()
    finish = LocationSerializer()
    vehicle = VehicleSerializer(source="*")
    route = RouteSerializer(source="*")
    fuel_stops = FuelStopSerializer(many=True, source="fuel_plan.stops")
    summary = SummarySerializer(source="fuel_plan")
    stations_considered = serializers.IntegerField()
    policy = PolicySerializer()
    external_api_calls = serializers.DictField(child=serializers.IntegerField())
    cached = serializers.BooleanField()
    map_url = serializers.SerializerMethodField()

    @extend_schema_field(serializers.URLField())
    def get_map_url(self, plan):
        request = self.context.get("request")
        path = reverse("map")
        url = request.build_absolute_uri(path) if request is not None else path
        query = {"start": plan.start.query, "finish": plan.finish.query}
        if plan.fuel_plan.starting_fuel_gallons != plan.vehicle.tank_capacity_gallons:
            query["starting_fuel_gallons"] = f"{plan.fuel_plan.starting_fuel_gallons:g}"
        return f"{url}?{urlencode(query)}"


class ErrorDetailSerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()
    details = serializers.DictField(required=False)


class ErrorSerializer(serializers.Serializer):
    error = ErrorDetailSerializer()
