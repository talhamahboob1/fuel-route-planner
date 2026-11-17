from unittest import mock

import requests
from django.test import SimpleTestCase

from routing.clients.osrm import OSRMClient
from routing.exceptions import ExternalServiceError, RouteNotFound
from routing.types import Coordinate


def fake_response(payload, status_code=200):
    response = mock.Mock()
    response.status_code = status_code
    response.ok = status_code < 400
    response.json.return_value = payload
    return response


class OSRMClientTests(SimpleTestCase):
    def setUp(self):
        self.session = mock.Mock()
        self.client = OSRMClient(base_url="https://osrm.example", session=self.session)
        self.start = Coordinate(41.8781, -87.6298)
        self.finish = Coordinate(38.627, -90.1994)

    def test_route_is_parsed(self):
        self.session.get.return_value = fake_response(
            {
                "code": "Ok",
                "routes": [
                    {
                        "distance": 477336.9,
                        "duration": 20210.9,
                        "geometry": {"type": "LineString", "coordinates": [[-87.63, 41.88], [-90.2, 38.63]]},
                    }
                ],
            }
        )

        route = self.client.route(self.start, self.finish)

        self.assertAlmostEqual(route.distance_miles, 296.6, places=1)
        self.assertAlmostEqual(route.duration_minutes, 336.8, places=1)
        self.assertEqual(route.coordinates[0], Coordinate(41.88, -87.63))
        url = self.session.get.call_args.args[0]
        self.assertEqual(url, "https://osrm.example/route/v1/driving/-87.629800,41.878100;-90.199400,38.627000")
        self.assertEqual(self.session.get.call_args.kwargs["params"]["overview"], "full")

    def test_no_route_raises_route_not_found(self):
        self.session.get.return_value = fake_response({"code": "NoRoute", "message": "Impossible route"}, 400)

        with self.assertRaises(RouteNotFound):
            self.client.route(self.start, self.finish)

    def test_network_errors_raise_external_service_error(self):
        self.session.get.side_effect = requests.ConnectionError("boom")

        with self.assertRaises(ExternalServiceError):
            self.client.route(self.start, self.finish)

    def test_rate_limiting_raises_external_service_error(self):
        self.session.get.return_value = fake_response({}, 429)

        with self.assertRaises(ExternalServiceError):
            self.client.route(self.start, self.finish)

    def test_unexpected_payload_raises_external_service_error(self):
        self.session.get.return_value = fake_response(
            {"code": "Ok", "routes": [{"distance": 1, "duration": 1, "geometry": {}}]}
        )

        with self.assertRaises(ExternalServiceError):
            self.client.route(self.start, self.finish)
