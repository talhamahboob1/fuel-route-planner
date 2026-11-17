from django.views.generic import TemplateView
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from routing.exceptions import ExternalServiceError, LocationNotFound, RouteNotFound
from stations.models import FuelStation

from .exceptions import (
    LocationNotFoundAPIError,
    RouteNotFoundAPIError,
    TripNotFeasibleAPIError,
    UpstreamUnavailableAPIError,
)
from .planner import InfeasibleTrip
from .serializers import ErrorSerializer, TripPlanRequestSerializer, TripPlanSerializer
from .services import TripPlanner, TripPlanRequest

PLAN_RESPONSES = {
    200: TripPlanSerializer,
    400: ErrorSerializer,
    422: ErrorSerializer,
    503: ErrorSerializer,
}
PLAN_DESCRIPTION = (
    "Routes between two locations in the USA, finds truck stops along the way and picks the "
    "cheapest places to buy fuel given the vehicle range. Returns the route geometry, every "
    "recommended stop with how much to buy there, and the total fuel spend."
)


class TripPlanView(APIView):
    @extend_schema(
        summary="Plan a route with the most cost effective fuel stops",
        description=PLAN_DESCRIPTION,
        parameters=[TripPlanRequestSerializer],
        responses=PLAN_RESPONSES,
        examples=[
            OpenApiExample(
                "City pair", value={"start": "Los Angeles, CA", "finish": "New York, NY"}, request_only=True
            ),
        ],
    )
    def get(self, request):
        return self._plan(request, request.query_params)

    @extend_schema(
        summary="Plan a route with the most cost effective fuel stops",
        description=PLAN_DESCRIPTION,
        request=TripPlanRequestSerializer,
        responses=PLAN_RESPONSES,
    )
    def post(self, request):
        return self._plan(request, request.data)

    def _plan(self, request, data):
        serializer = TripPlanRequestSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        params = dict(serializer.validated_data)
        include_geometry = params.pop("include_geometry", True)

        try:
            plan = TripPlanner().plan(TripPlanRequest(**params))
        except LocationNotFound as exc:
            raise LocationNotFoundAPIError(exc.message, details={"field": exc.field, "query": exc.query}) from exc
        except RouteNotFound as exc:
            raise RouteNotFoundAPIError(str(exc)) from exc
        except InfeasibleTrip as exc:
            raise TripNotFeasibleAPIError(
                exc.message,
                details={
                    "gap_start_miles": round(exc.gap_start_miles, 1),
                    "gap_end_miles": round(exc.gap_end_miles, 1),
                },
            ) from exc
        except ExternalServiceError as exc:
            raise UpstreamUnavailableAPIError(exc.message, details={"service": exc.service}) from exc

        output = TripPlanSerializer(plan, context={"request": request, "include_geometry": include_geometry})
        return Response(output.data)


class HealthView(APIView):
    throttle_classes = []

    @extend_schema(summary="Service health and loaded station counts", responses={200: dict})
    def get(self, request):
        total = FuelStation.objects.count()
        geocoded = FuelStation.objects.filter(latitude__isnull=False).count()
        return Response({"status": "ok", "stations_loaded": total, "stations_geocoded": geocoded})


class MapPageView(TemplateView):
    template_name = "map.html"
