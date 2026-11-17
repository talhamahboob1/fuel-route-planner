from django.test import SimpleTestCase

from stations.gazetteer import Gazetteer, Place, compact_city_name, normalize_city_name
from stations.us_states import normalize_state


class NormalizationTests(SimpleTestCase):
    def test_city_names_are_upper_cased_and_trimmed(self):
        self.assertEqual(normalize_city_name("  Chicago   "), "CHICAGO")
        self.assertEqual(normalize_city_name("new   castle"), "NEW CASTLE")

    def test_leading_abbreviations_are_expanded(self):
        self.assertEqual(normalize_city_name("St. Louis"), "SAINT LOUIS")
        self.assertEqual(normalize_city_name("Ft Smith"), "FORT SMITH")
        self.assertEqual(normalize_city_name("Mt Jackson"), "MOUNT JACKSON")
        self.assertEqual(normalize_city_name("N Little Rock"), "NORTH LITTLE ROCK")

    def test_compact_name_removes_spaces(self):
        self.assertEqual(compact_city_name("De Forest"), "DEFOREST")

    def test_state_codes_and_names(self):
        self.assertEqual(normalize_state("tx"), "TX")
        self.assertEqual(normalize_state(" Texas "), "TX")
        self.assertEqual(normalize_state("new york"), "NY")
        self.assertIsNone(normalize_state("Ontario"))
        self.assertIsNone(normalize_state(""))


class GazetteerLookupTests(SimpleTestCase):
    def setUp(self):
        self.gazetteer = Gazetteer(
            [
                Place("Deforest", "WI", 43.2478, -89.3437, 1),
                Place("Saint Louis", "MO", 38.63, -90.2, 60),
                Place("Springfield", "IL", 39.8, -89.65, 20),
                Place("Springfield", "MO", 37.2, -93.3, 25),
            ]
        )

    def test_exact_lookup_is_case_insensitive(self):
        place = self.gazetteer.lookup("springfield", "il")
        self.assertEqual((place.latitude, place.longitude), (39.8, -89.65))

    def test_state_disambiguates_same_city_name(self):
        self.assertEqual(self.gazetteer.lookup("Springfield", "MO").longitude, -93.3)

    def test_abbreviated_city_matches_expanded_place(self):
        self.assertEqual(self.gazetteer.lookup("St. Louis", "MO").latitude, 38.63)

    def test_compact_fallback_matches_spacing_differences(self):
        self.assertEqual(self.gazetteer.lookup("De Forest", "WI").latitude, 43.2478)

    def test_unknown_place_returns_none(self):
        self.assertIsNone(self.gazetteer.lookup("Nowhere", "WI"))
        self.assertIsNone(self.gazetteer.lookup("", "WI"))
