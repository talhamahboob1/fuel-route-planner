import tempfile
from decimal import Decimal
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from stations.models import FuelStation

HEADER = "OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price\n"


def write_csv(rows):
    handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8")
    handle.write(HEADER)
    handle.writelines(rows)
    handle.close()
    return handle.name


class LoadStationsCommandTests(TestCase):
    def setUp(self):
        self.csv_path = write_csv(
            [
                '7,WOODSHED OF BIG CABIN,"I-44, EXIT 283 & US-69",Big Cabin,OK,307,3.00733333\n',
                '105,TA SAGINAW,"I-75, EXIT 144-B",Bridgeport,MI,260,3.269\n',
                '105,TA SAGINAW,"I-75, EXIT 144-B",Bridgeport,MI,260,3.339\n',
                '105,TA SAGINAW,"I-75, EXIT 144-B",Bridgeport,MI,260,3.429\n',
                '900,FLYING J,"HWY 1",Abbotsford,BC,999,4.100\n',
                '901,LOST STOP,"I-10",Nowhereville Imaginary,TX,10,2.999\n',
                "79,DELAWARE TRUCK PLAZA,US-13 & US-40,New Castle                   ,DE,243,3.249\n",
            ]
        )

    def tearDown(self):
        Path(self.csv_path).unlink(missing_ok=True)

    def run_command(self, *args):
        output = StringIO()
        call_command("load_stations", "--csv", self.csv_path, *args, stdout=output)
        return output.getvalue()

    def test_rows_are_deduplicated_averaged_and_geocoded(self):
        output = self.run_command()

        self.assertEqual(FuelStation.objects.count(), 4)
        saginaw = FuelStation.objects.get(opis_id=105)
        self.assertEqual(saginaw.retail_price, Decimal("3.346"))
        self.assertEqual(saginaw.price_samples, 3)
        self.assertTrue(saginaw.has_coordinates)

        big_cabin = FuelStation.objects.get(opis_id=7)
        self.assertEqual(big_cabin.retail_price, Decimal("3.007"))
        self.assertAlmostEqual(big_cabin.latitude, 36.534, places=2)

        new_castle = FuelStation.objects.get(opis_id=79)
        self.assertEqual(new_castle.city, "New Castle")
        self.assertTrue(new_castle.has_coordinates)

        self.assertFalse(FuelStation.objects.filter(opis_id=900).exists())
        self.assertFalse(FuelStation.objects.get(opis_id=901).has_coordinates)
        self.assertIn("Skipped 1 rows outside the USA", output)
        self.assertIn("No coordinates for Nowhereville Imaginary, TX", output)

    def test_reloading_updates_in_place(self):
        self.run_command()
        FuelStation.objects.filter(opis_id=7).update(retail_price=Decimal("9.999"))

        self.run_command()

        self.assertEqual(FuelStation.objects.count(), 4)
        self.assertEqual(FuelStation.objects.get(opis_id=7).retail_price, Decimal("3.007"))

    def test_purge_removes_stations_missing_from_file(self):
        FuelStation.objects.create(
            opis_id=5555, name="Old", address="", city="Dallas", state="TX", rack_id=1, retail_price=Decimal("3.1")
        )

        self.run_command("--purge")

        self.assertFalse(FuelStation.objects.filter(opis_id=5555).exists())
        self.assertEqual(FuelStation.objects.count(), 4)

    def test_missing_file_raises_command_error(self):
        with self.assertRaises(CommandError):
            call_command("load_stations", "--csv", "/nonexistent/file.csv", stdout=StringIO())

    def test_missing_columns_raise_command_error(self):
        path = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8")
        path.write("Name,City\nX,Y\n")
        path.close()
        try:
            with self.assertRaises(CommandError):
                call_command("load_stations", "--csv", path.name, stdout=StringIO())
        finally:
            Path(path.name).unlink(missing_ok=True)
