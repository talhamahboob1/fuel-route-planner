from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.views import exception_handler


class PlanningAPIError(APIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "The trip could not be planned."
    default_code = "trip_not_plannable"

    def __init__(self, detail=None, code=None, details=None):
        super().__init__(detail, code)
        self.details = details or {}


class LocationNotFoundAPIError(PlanningAPIError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "A location could not be found."
    default_code = "location_not_found"


class RouteNotFoundAPIError(PlanningAPIError):
    default_detail = "No drivable route was found."
    default_code = "route_not_found"


class TripNotFeasibleAPIError(PlanningAPIError):
    default_detail = "The vehicle cannot complete this trip with the known fuel stations."
    default_code = "trip_not_feasible"


class UpstreamUnavailableAPIError(PlanningAPIError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "An external service is unavailable."
    default_code = "upstream_unavailable"


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None
    if isinstance(exc, ValidationError):
        payload = {
            "code": "validation_error",
            "message": "The request parameters are invalid.",
            "details": exc.detail,
        }
    else:
        codes = exc.get_codes() if isinstance(exc, APIException) else "error"
        payload = {
            "code": codes if isinstance(codes, str) else "error",
            "message": str(exc.detail) if isinstance(exc, APIException) else str(exc),
            "details": getattr(exc, "details", None) or {},
        }
    response.data = {"error": payload}
    return response
