import numpy as np

from routing.geometry import MILES_PER_DEGREE, nearest_route_points, resample_route

from .planner import RouteStation


def find_stations_along_route(route, index, max_detour_miles, spacing_miles):
    if len(index) == 0 or len(route.coordinates) < 2:
        return []

    lats = np.array([point.latitude for point in route.coordinates], dtype=np.float64)
    lons = np.array([point.longitude for point in route.coordinates], dtype=np.float64)
    sample_lats, sample_lons, sample_distances = resample_route(
        lats, lons, spacing_miles, total_miles=route.distance_miles
    )

    lat_margin = max_detour_miles / MILES_PER_DEGREE
    lon_margin = lat_margin / max(np.cos(np.radians(np.abs(lats).max())), 0.1)
    in_box = (
        (index.latitudes >= lats.min() - lat_margin)
        & (index.latitudes <= lats.max() + lat_margin)
        & (index.longitudes >= lons.min() - lon_margin)
        & (index.longitudes <= lons.max() + lon_margin)
    )
    candidate_ids = np.flatnonzero(in_box)
    if len(candidate_ids) == 0:
        return []

    nearest, distances = nearest_route_points(
        sample_lats, sample_lons, index.latitudes[candidate_ids], index.longitudes[candidate_ids]
    )
    results = []
    for offset, record_index in enumerate(candidate_ids):
        if distances[offset] > max_detour_miles:
            continue
        results.append(
            RouteStation(
                station=index.records[int(record_index)],
                distance_from_start_miles=float(sample_distances[nearest[offset]]),
                distance_from_route_miles=float(distances[offset]),
            )
        )
    results.sort(key=lambda item: (item.distance_from_start_miles, item.price_per_gallon))
    return results
