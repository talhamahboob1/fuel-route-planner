# Data files

## fuel-prices-for-be-assessment.csv

The OPIS truck stop price list supplied with the assignment. Columns: OPIS Truckstop ID, Truckstop Name, Address, City, State, Rack ID, Retail Price. Loaded with `python manage.py load_stations`.

## us_places.csv

A gazetteer of US places with coordinates, used to geocode the stations and to resolve "City, ST" inputs without a network call. Columns: city, state, latitude, longitude, postal_codes.

It was derived from the GeoNames postal code export for the United States (https://download.geonames.org/export/zip/), grouping the ZIP code rows by place name and state and averaging their coordinates. The GeoNames data is licensed under the Creative Commons Attribution 4.0 License, https://creativecommons.org/licenses/by/4.0/. Source: GeoNames, https://www.geonames.org/.
