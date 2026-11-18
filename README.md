# Fuel Route Planner

A Django REST API that plans a driving route between two locations in the USA and works out the most cost effective places to buy fuel along the way. It returns the route geometry for a map, every recommended fuel stop with how many gallons to buy there, and the total money spent on fuel. The vehicle is assumed to have a 500 mile range and to achieve 10 miles per gallon.

Each request makes exactly one call to the routing service. Geocoding of the start and finish is done offline for the common "City, ST" and "latitude,longitude" inputs, so the typical request never touches a geocoding API at all.

## Quick start

Requirements: Python 3.12 or newer. Django 6.1 does not support older interpreters.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python manage.py migrate
python manage.py load_stations
python manage.py runserver
```

`load_stations` reads `data/fuel-prices-for-be-assessment.csv`, deduplicates it, geocodes every station against the bundled gazetteer and stores the result. It takes about two seconds and prints a summary. Rerunning it is safe, it updates stations in place.

Then open:

| URL | What it is |
| --- | --- |
| `http://127.0.0.1:8000/api/v1/route/?start=Los+Angeles,+CA&finish=New+York,+NY` | The planning endpoint |
| `http://127.0.0.1:8000/` | Interactive map that calls the API and draws the route and the stops |
| `http://127.0.0.1:8000/api/docs/` | Swagger UI generated from the OpenAPI schema |
| `http://127.0.0.1:8000/api/v1/health/` | Health check with station counts |

If you prefer [uv](https://docs.astral.sh/uv/): `uv venv --python 3.12 && uv pip install -r requirements.txt`.

## Using the API

`GET /api/v1/route/` with query parameters, or `POST /api/v1/route/` with the same fields as a JSON body.

| Parameter | Required | Description |
| --- | --- | --- |
| `start` | yes | Start location inside the USA. Accepts `City, ST`, `City, State Name`, a full street address, or `latitude,longitude`. |
| `finish` | yes | Finish location, same formats. |
| `starting_fuel_gallons` | no | Fuel in the tank at departure. Defaults to a full tank (50 gallons). Cannot exceed the tank capacity. |
| `max_detour_miles` | no | How far off the route a station may sit and still count. Defaults to 10, capped at 50. |
| `include_geometry` | no | Set to `false` to leave the route geometry out of the response. |

```bash
curl "http://127.0.0.1:8000/api/v1/route/?start=Chicago,+IL&finish=Dallas,+TX"

curl -X POST http://127.0.0.1:8000/api/v1/route/ \
  -H "Content-Type: application/json" \
  -d '{"start": "Seattle, WA", "finish": "Miami, FL", "starting_fuel_gallons": 20}'
```

A trimmed response:

```json
{
  "start": {"query": "Chicago, IL", "label": "Chicago, IL", "latitude": 41.8542, "longitude": -87.676, "resolved_by": "gazetteer"},
  "finish": {"query": "Dallas, TX", "label": "Dallas, TX", "latitude": 32.7886, "longitude": -96.7872, "resolved_by": "gazetteer"},
  "vehicle": {"range_miles": 500.0, "miles_per_gallon": 10.0, "tank_capacity_gallons": 50.0, "starting_fuel_gallons": 50.0},
  "route": {
    "distance_miles": 966.9,
    "duration_minutes": 1026,
    "duration_text": "17h 06m",
    "bounding_box": {"south": 32.782521, "west": -96.787257, "north": 41.855086, "east": -87.624684},
    "geometry": {"type": "LineString", "coordinates": [[-87.6759, 41.8542], "..."]}
  },
  "fuel_stops": [
    {
      "sequence": 1,
      "station": {"opis_id": 66643, "name": "DEERFIELD TRAVEL CENTER", "address": "I-55, EXIT 8", "city": "Steele", "state": "MO", "latitude": 36.0915, "longitude": -89.8346},
      "distance_from_start_miles": 452.5,
      "distance_from_route_miles": 1.6,
      "price_per_gallon": 2.976,
      "gallons_purchased": 29.3,
      "cost": 87.2,
      "fuel_on_arrival_gallons": 4.75,
      "fuel_on_departure_gallons": 34.05
    },
    {"sequence": 2, "station": {"name": "Quiktrip #7900", "city": "Texarkana", "state": "TX", "...": "..."}, "gallons_purchased": 17.39, "cost": 49.68, "...": "..."}
  ],
  "summary": {
    "total_fuel_cost": 136.88,
    "total_gallons_purchased": 46.69,
    "total_gallons_consumed": 96.69,
    "fuel_stop_count": 2,
    "average_price_paid_per_gallon": 2.932,
    "fuel_at_finish_gallons": 0.0,
    "currency": "USD"
  },
  "stations_considered": 188,
  "policy": {"max_detour_miles": 10.0, "min_purchase_gallons": 5.0, "min_price_drop_per_gallon": 0.1},
  "external_api_calls": {"routing": 1, "geocoding": 0},
  "cached": false,
  "map_url": "http://127.0.0.1:8000/?start=Chicago%2C+IL&finish=Dallas%2C+TX"
}
```

`route.geometry` is a GeoJSON LineString, so it can be dropped straight onto Leaflet, Mapbox or any GIS tool. `map_url` opens the bundled map page for the same trip.

Errors share one shape, `{"error": {"code": "...", "message": "...", "details": {...}}}`:

| Status | Code | When |
| --- | --- | --- |
| 400 | `validation_error` | Missing or invalid parameters. `details` lists the field errors. |
| 400 | `location_not_found` | A location could not be resolved, or it is outside the USA. `details.field` says which one. |
| 422 | `route_not_found` | The routing service found no drivable route, for example to Hawaii. |
| 422 | `trip_not_feasible` | A stretch of the route longer than the vehicle range has no known station. |
| 429 | `throttled` | The anonymous rate limit was hit (120 requests per minute by default). |
| 503 | `upstream_unavailable` | The routing or geocoding service failed. `details.service` says which one. |

## How a request is handled

1. **Resolve the locations.** Coordinates are used as given. `City, ST` style input is looked up in a bundled gazetteer of about 29,500 US places, with no network call. Anything else goes to Nominatim, and the answer is stored in the database so the same address never costs a second call. Every result is checked against US bounding boxes.
2. **Route once.** A single request to the public OSRM server returns the full driving geometry, distance and duration. The geometry is requested as an encoded polyline, which is about a quarter of the size of GeoJSON on the wire.
3. **Find stations along the route.** The geometry is resampled every half mile. Stations inside the route's bounding box are compared against those samples with vectorised numpy, and the ones within `max_detour_miles` of the road are kept, each tagged with its mile marker along the route.
4. **Plan the fuel stops** (see below).
5. **Simplify the geometry** for the response with Douglas Peucker at a 30 metre tolerance, which cuts a coast to coast route from about 35,000 points to about 3,500 without visible change on a map.
6. **Cache the plan** for an hour on disk, keyed on the normalised inputs. A repeat request returns in a few milliseconds, makes no external calls, and the cache survives a server restart.

A cold coast to coast request takes between one and three seconds, almost all of it waiting for OSRM. The local work (candidate search, planning, simplification) takes under half a second for the longest routes in the country.

## The fuel plan

Assumptions, all configurable through settings:

* The vehicle starts with a full tank (50 gallons, 500 miles). Pass `starting_fuel_gallons` to model anything else. With a full tank, trips under 500 miles need no stops and cost nothing, which the response states explicitly.
* Fuel prices are the retail prices from the CSV, in US dollars per gallon.
* The vehicle is allowed to arrive at the finish with an empty tank.
* The small detour to a station is not charged. Stations are only considered when they lie within `max_detour_miles` of the route (10 miles by default), and the response reports the actual distance off route for each stop.

The core is the classic exact solution to the fixed route refuelling problem. Walking the route station by station:

* if a cheaper station is within range, buy only enough fuel to reach it;
* otherwise this station is the cheapest reachable one, so fill the tank, or buy just enough to reach the finish if it is within range.

That greedy rule is provably cost optimal for a fixed tank capacity, but applied literally it produces a long chain of tiny purchases whenever prices fall gradually along a highway. Two practical rules sit on top of it:

* **Minimum price drop** (`MIN_PRICE_DROP_PER_GALLON`, 10 cents by default). A later station only justifies a separate stop if it is at least this much cheaper. When the only cheaper stations ahead are marginally cheaper, the planner buys enough here to reach the cheapest one of them, or the finish, in one go.
* **Minimum purchase** (`MIN_PURCHASE_GALLONS`, 5 by default). Optional purchases below this size are skipped, and purchases the plan cannot do without are raised to this size.

On real routes this cuts the number of stops by a quarter to a half while keeping the cost within about one percent of the exact optimum. Set both to zero to get the textbook optimum. Several stations in the same city share coordinates, so at each mile marker only the cheapest one is considered.

Feasibility is checked up front. If two consecutive known stations are more than 500 miles apart along the route, or the starting fuel cannot reach the first one, the API returns `trip_not_feasible` with the mile markers of the gap.

## Data

**Fuel prices.** `data/fuel-prices-for-be-assessment.csv` is the OPIS extract supplied with the assignment: 8,151 rows, 6,738 distinct truck stops. 678 stops appear several times with different price snapshots and no date column, so the loader stores one row per OPIS id with the average of its prices and keeps the sample count. The 620 rows for Canadian provinces are skipped because both ends of a trip must be in the USA. Prices are rounded to a tenth of a cent, which is how fuel is priced at the pump.

**Geocoding.** The CSV has street level descriptions such as "I-44, EXIT 283 & US-69" that no geocoder resolves reliably, but it has clean city and state columns. `data/us_places.csv` is a gazetteer derived from the GeoNames postal code dataset: one row per place and state with the average coordinates of its ZIP codes. City names are normalised before matching (case, punctuation, "St." to "Saint", "Ft" to "Fort", and so on). Every one of the 6,626 US stations resolves. City centroids are typically within a few miles of the truck stop itself, which is well inside the default detour radius. The same gazetteer resolves "City, ST" inputs for the start and finish without any API call.

GeoNames data is licensed under [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/). See `data/README.md`.

## External services

| Service | Used for | Calls per request |
| --- | --- | --- |
| [OSRM demo server](https://project-osrm.org/) | Driving route, distance, duration, geometry | 1 (0 when the plan is cached) |
| [Nominatim](https://nominatim.org/) | Fallback geocoding for free text addresses | 0 for coordinates or `City, ST`, otherwise 1 per location, cached forever after |

Both are free and need no API key. Their usage policies ask for an identifying `User-Agent`, which `HTTP_USER_AGENT` sets, and modest request rates, which the API throttle and the result cache help with. The public OSRM server is shared and its response time varies from one to several seconds, occasionally more, so the client retries a failed call once (`HTTP_RETRIES`) and gives up after `HTTP_TIMEOUT_SECONDS`. For production use point `OSRM_BASE_URL` at your own OSRM instance.

## Configuration

Settings are read from environment variables. `.env.example` lists them all.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS` | development values | Standard Django settings |
| `DATABASE_URL` | SQLite file | Any database URL supported by dj-database-url, for example Postgres |
| `VEHICLE_RANGE_MILES` | 500 | Vehicle range on a full tank |
| `VEHICLE_MILES_PER_GALLON` | 10 | Fuel economy |
| `MAX_DETOUR_MILES` | 10 | Default distance a station may be off route |
| `MIN_PURCHASE_GALLONS` | 5 | Smallest purchase the planner will suggest |
| `MIN_PRICE_DROP_PER_GALLON` | 0.10 | Price advantage needed to justify an extra stop |
| `RESULT_CACHE_SECONDS` | 3600 | How long a plan is cached |
| `CACHE_DIR` | `.cache` in the project | Where the file based cache lives |
| `API_THROTTLE_RATE` | 120/min | Anonymous rate limit |
| `OSRM_BASE_URL`, `NOMINATIM_BASE_URL`, `HTTP_USER_AGENT`, `HTTP_TIMEOUT_SECONDS`, `HTTP_RETRIES` | public servers, 15 s, 1 retry | External service settings |

## Tests

```bash
python manage.py test
```

The suite covers the CSV loader, gazetteer matching, geocoding resolution order, the OSRM client, the geometry helpers, the planner (including the feasibility checks and the practical rules), the candidate search and the API end to end with a mocked routing service. No test touches the network.

## Project layout

```
config/      settings, urls, wsgi, asgi
stations/    FuelStation model, gazetteer, load_stations command, in memory station index
routing/     OSRM and Nominatim clients, geocoder, route geometry maths, geocode cache model
trips/       fuel stop planner, candidate search, service layer, API serializers and views
templates/   the Leaflet map page
data/        fuel price CSV and the GeoNames derived gazetteer
```

## Running with Docker

```bash
docker build -t fuel-route-planner .
docker run --rm -p 8000:8000 fuel-route-planner
```

The container runs migrations, loads the stations and serves the app with gunicorn on port 8000.

## Production notes

* Use Postgres through `DATABASE_URL` and set `DJANGO_DEBUG=false` with a real secret key and allowed hosts.
* The plan cache is file based, so every gunicorn worker on a host shares it and it survives restarts. Across several hosts switch `CACHES` to Redis or Memcached.
* The station index is built in memory per process from the database (about 6,600 rows) and refreshes itself whenever the station table changes.
* The USA check for coordinates uses bounding boxes for the contiguous states, Alaska and Hawaii. It rejects obvious mistakes, not every point just across the Canadian or Mexican border.
