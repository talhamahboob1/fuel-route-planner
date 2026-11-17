from unittest import mock

from django.test import TestCase

from routing.clients.nominatim import GeocodedPlace
from routing.exceptions import LocationNotFound, LocationOutsideUSA
from routing.geocoding import Geocoder, parse_coordinates, split_city_state
from routing.models import GeocodeCacheEntry
from routing.types import Coordinate
from stations.gazetteer import Gazetteer, Place


class ParsingTests(TestCase):
    def test_coordinates_are_parsed(self):
        self.assertEqual(parse_coordinates("41.8781, -87.6298"), Coordinate(41.8781, -87.6298))
        self.assertEqual(parse_coordinates("41,-87"), Coordinate(41.0, -87.0))
        self.assertIsNone(parse_coordinates("Chicago, IL"))

    def test_out_of_range_coordinates_are_rejected(self):
        with self.assertRaises(LocationNotFound):
            parse_coordinates("95.0, -87.0")

    def test_city_and_state_are_split(self):
        self.assertEqual(split_city_state("Dallas, TX"), ("Dallas", "TX"))
        self.assertEqual(split_city_state("Dallas, Texas"), ("Dallas", "TX"))
        self.assertEqual(split_city_state("Dallas TX"), ("Dallas", "TX"))
        self.assertEqual(split_city_state("Dallas, TX, USA"), ("Dallas", "TX"))
        self.assertEqual(split_city_state("Santa Fe New Mexico"), ("Santa Fe", "NM"))
        self.assertEqual(split_city_state("Washington, DC"), ("Washington", "DC"))

    def test_inputs_without_a_state_are_not_split(self):
        self.assertIsNone(split_city_state("Dallas"))
        self.assertIsNone(split_city_state("123 Main Street"))
        self.assertIsNone(split_city_state("Toronto, ON"))


class GeocoderTests(TestCase):
    def setUp(self):
        self.gazetteer = Gazetteer([Place("Dallas", "TX", 32.78, -96.8, 50)])
        self.client = mock.Mock()
        self.geocoder = Geocoder(gazetteer=self.gazetteer, client=self.client)

    def test_coordinates_inside_usa_resolve_without_lookups(self):
        location = self.geocoder.resolve(" 41.8781 , -87.6298 ")

        self.assertEqual(location.source, "coordinates")
        self.assertEqual(location.coordinate, Coordinate(41.8781, -87.6298))
        self.client.geocode.assert_not_called()

    def test_coordinates_outside_usa_are_rejected(self):
        with self.assertRaises(LocationOutsideUSA):
            self.geocoder.resolve("48.8566, 2.3522")

    def test_city_state_resolves_from_gazetteer(self):
        location = self.geocoder.resolve("dallas, texas")

        self.assertEqual(location.source, "gazetteer")
        self.assertEqual(location.label, "Dallas, TX")
        self.assertEqual(location.coordinate, Coordinate(32.78, -96.8))
        self.client.geocode.assert_not_called()

    def test_cached_queries_skip_the_remote_service(self):
        GeocodeCacheEntry.objects.create(
            query_key="1600 pennsylvania ave, washington, dc",
            query="1600 Pennsylvania Ave, Washington, DC",
            display_name="White House",
            latitude=38.8977,
            longitude=-77.0365,
        )

        location = self.geocoder.resolve("1600 Pennsylvania  Ave, Washington, DC")

        self.assertEqual(location.source, "cache")
        self.assertEqual(location.label, "White House")
        self.client.geocode.assert_not_called()

    def test_remote_results_are_validated_and_cached(self):
        self.client.geocode.return_value = GeocodedPlace(Coordinate(36.17, -115.14), "Las Vegas Strip, NV")

        location = self.geocoder.resolve("Las Vegas Strip")

        self.assertEqual(location.source, "nominatim")
        self.assertEqual(location.coordinate, Coordinate(36.17, -115.14))
        self.client.geocode.assert_called_once_with("Las Vegas Strip")
        entry = GeocodeCacheEntry.objects.get(query_key="las vegas strip")
        self.assertEqual(entry.display_name, "Las Vegas Strip, NV")

    def test_remote_results_outside_usa_are_rejected(self):
        self.client.geocode.return_value = GeocodedPlace(Coordinate(19.43, -99.13), "Mexico City")

        with self.assertRaises(LocationOutsideUSA):
            self.geocoder.resolve("Mexico City downtown")
        self.assertFalse(GeocodeCacheEntry.objects.exists())

    def test_unknown_places_raise(self):
        self.client.geocode.return_value = None

        with self.assertRaises(LocationNotFound):
            self.geocoder.resolve("Some place that does not exist")

    def test_blank_input_raises(self):
        with self.assertRaises(LocationNotFound):
            self.geocoder.resolve("   ")
