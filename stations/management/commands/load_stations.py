import csv
from collections import OrderedDict
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from stations.gazetteer import get_gazetteer
from stations.index import invalidate_station_index
from stations.models import FuelStation
from stations.us_states import US_STATES

REQUIRED_COLUMNS = (
    "OPIS Truckstop ID",
    "Truckstop Name",
    "Address",
    "City",
    "State",
    "Rack ID",
    "Retail Price",
)
PRICE_PRECISION = Decimal("0.001")


class Command(BaseCommand):
    help = "Load truck stop fuel prices from the OPIS CSV file and geocode them with the bundled gazetteer."

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv",
            dest="csv_path",
            default=str(settings.FUEL_ROUTER["STATIONS_CSV_PATH"]),
            help="Path to the fuel prices CSV file.",
        )
        parser.add_argument(
            "--purge",
            action="store_true",
            help="Remove stations from the database that are not present in the CSV file.",
        )

    def handle(self, *args, **options):
        csv_path = Path(options["csv_path"])
        if not csv_path.exists():
            raise CommandError(f"CSV file not found: {csv_path}")

        groups, skipped_non_us, skipped_invalid = self.read_groups(csv_path)
        gazetteer = get_gazetteer()
        stations = []
        unmatched = OrderedDict()
        for group in groups.values():
            place = gazetteer.lookup(group["city"], group["state"])
            if place is None:
                unmatched.setdefault((group["city"], group["state"]), 0)
                unmatched[(group["city"], group["state"])] += 1
            average = sum(group["prices"]) / len(group["prices"])
            stations.append(
                FuelStation(
                    opis_id=group["opis_id"],
                    name=group["name"],
                    address=group["address"],
                    city=group["city"],
                    state=group["state"],
                    rack_id=group["rack_id"],
                    retail_price=average.quantize(PRICE_PRECISION, rounding=ROUND_HALF_UP),
                    price_samples=len(group["prices"]),
                    latitude=place.latitude if place else None,
                    longitude=place.longitude if place else None,
                )
            )

        with transaction.atomic():
            FuelStation.objects.bulk_create(
                stations,
                batch_size=500,
                update_conflicts=True,
                unique_fields=["opis_id"],
                update_fields=[
                    "name",
                    "address",
                    "city",
                    "state",
                    "rack_id",
                    "retail_price",
                    "price_samples",
                    "latitude",
                    "longitude",
                    "updated_at",
                ],
            )
            purged = 0
            if options["purge"]:
                purged, _ = FuelStation.objects.exclude(opis_id__in=groups.keys()).delete()
        invalidate_station_index()

        geocoded = sum(1 for station in stations if station.latitude is not None)
        self.stdout.write(f"Read {sum(len(g['prices']) for g in groups.values())} US rows from {csv_path.name}")
        self.stdout.write(f"Skipped {skipped_non_us} rows outside the USA and {skipped_invalid} malformed rows")
        missing = len(stations) - geocoded
        self.stdout.write(
            f"Stored {len(stations)} unique stations ({geocoded} geocoded, {missing} without coordinates)"
        )
        if purged:
            self.stdout.write(f"Purged {purged} stations that were not in the file")
        for (city, state), count in unmatched.items():
            self.stdout.write(self.style.WARNING(f"No coordinates for {city}, {state} ({count} stations)"))
        self.stdout.write(self.style.SUCCESS("Station load complete"))

    def read_groups(self, csv_path):
        groups = OrderedDict()
        skipped_non_us = 0
        skipped_invalid = 0
        with open(csv_path, newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            missing = [column for column in REQUIRED_COLUMNS if column not in (reader.fieldnames or [])]
            if missing:
                raise CommandError(f"CSV is missing required columns: {', '.join(missing)}")
            for row in reader:
                state = (row["State"] or "").strip().upper()
                if state not in US_STATES:
                    skipped_non_us += 1
                    continue
                try:
                    opis_id = int(row["OPIS Truckstop ID"])
                    rack_id = int(row["Rack ID"])
                    price = Decimal(row["Retail Price"].strip())
                except (TypeError, ValueError, InvalidOperation):
                    skipped_invalid += 1
                    continue
                if price <= 0:
                    skipped_invalid += 1
                    continue
                group = groups.get(opis_id)
                if group is None:
                    groups[opis_id] = {
                        "opis_id": opis_id,
                        "name": " ".join(row["Truckstop Name"].split()),
                        "address": " ".join((row["Address"] or "").split()),
                        "city": " ".join(row["City"].split()),
                        "state": state,
                        "rack_id": rack_id,
                        "prices": [price],
                    }
                else:
                    group["prices"].append(price)
        return groups, skipped_non_us, skipped_invalid
