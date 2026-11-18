from django.test import SimpleTestCase

from routing.polyline import decode_polyline
from routing.types import Coordinate


class DecodePolylineTests(SimpleTestCase):
    def test_reference_vector_decodes(self):
        points = decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@")

        self.assertEqual(points, [Coordinate(38.5, -120.2), Coordinate(40.7, -120.95), Coordinate(43.252, -126.453)])

    def test_empty_string_decodes_to_nothing(self):
        self.assertEqual(decode_polyline(""), [])

    def test_truncated_input_raises(self):
        with self.assertRaises(ValueError):
            decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq")
