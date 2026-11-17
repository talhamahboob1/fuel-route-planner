import math

import numpy as np

from .types import METERS_PER_MILE

EARTH_RADIUS_MILES = 3958.7613
MILES_PER_DEGREE = 2.0 * math.pi * EARTH_RADIUS_MILES / 360.0


def haversine_miles(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = (np.radians(np.asarray(value, dtype=np.float64)) for value in (lat1, lon1, lat2, lon2))
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    chord = np.sin(delta_lat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(delta_lon / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(np.clip(chord, 0.0, 1.0)))


def cumulative_distances_miles(lats, lons):
    lats = np.asarray(lats, dtype=np.float64)
    lons = np.asarray(lons, dtype=np.float64)
    if len(lats) < 2:
        return np.zeros(len(lats), dtype=np.float64)
    steps = haversine_miles(lats[:-1], lons[:-1], lats[1:], lons[1:])
    return np.concatenate(([0.0], np.cumsum(steps)))


def resample_route(lats, lons, spacing_miles, total_miles=None):
    lats = np.asarray(lats, dtype=np.float64)
    lons = np.asarray(lons, dtype=np.float64)
    cumulative = cumulative_distances_miles(lats, lons)
    measured = cumulative[-1] if len(cumulative) else 0.0
    if total_miles and measured > 0:
        cumulative = cumulative * (total_miles / measured)
    total = cumulative[-1] if len(cumulative) else 0.0
    if total <= 0 or len(lats) < 2:
        return lats[:1], lons[:1], np.zeros(min(len(lats), 1), dtype=np.float64)
    targets = np.arange(0.0, total, spacing_miles)
    if targets[-1] < total:
        targets = np.append(targets, total)
    return np.interp(targets, cumulative, lats), np.interp(targets, cumulative, lons), targets


def nearest_route_points(route_lats, route_lons, point_lats, point_lons, chunk_size=256):
    route_lats = np.asarray(route_lats, dtype=np.float64)
    route_lons = np.asarray(route_lons, dtype=np.float64)
    point_lats = np.asarray(point_lats, dtype=np.float64)
    point_lons = np.asarray(point_lons, dtype=np.float64)
    indices = np.empty(len(point_lats), dtype=np.int64)
    distances = np.empty(len(point_lats), dtype=np.float64)
    route_y = route_lats * MILES_PER_DEGREE
    for start in range(0, len(point_lats), chunk_size):
        end = start + chunk_size
        scale = (np.cos(np.radians(point_lats[start:end])) * MILES_PER_DEGREE)[:, None]
        delta_x = (point_lons[start:end, None] - route_lons[None, :]) * scale
        delta_y = point_lats[start:end, None] * MILES_PER_DEGREE - route_y[None, :]
        squared = delta_x * delta_x + delta_y * delta_y
        nearest = np.argmin(squared, axis=1)
        indices[start:end] = nearest
        distances[start:end] = np.sqrt(squared[np.arange(len(nearest)), nearest])
    return indices, distances


def douglas_peucker_mask(xs, ys, tolerance):
    count = len(xs)
    keep = np.zeros(count, dtype=bool)
    if count == 0:
        return keep
    keep[0] = True
    keep[-1] = True
    stack = [(0, count - 1)]
    while stack:
        first, last = stack.pop()
        if last - first < 2:
            continue
        start_x, start_y, end_x, end_y = xs[first], ys[first], xs[last], ys[last]
        segment_x = xs[first + 1 : last]
        segment_y = ys[first + 1 : last]
        delta_x = end_x - start_x
        delta_y = end_y - start_y
        length = math.hypot(delta_x, delta_y)
        if length == 0:
            offsets = np.hypot(segment_x - start_x, segment_y - start_y)
        else:
            offsets = np.abs(delta_y * segment_x - delta_x * segment_y + end_x * start_y - end_y * start_x) / length
        furthest = int(np.argmax(offsets))
        if offsets[furthest] > tolerance:
            split = first + 1 + furthest
            keep[split] = True
            stack.append((first, split))
            stack.append((split, last))
    return keep


def simplify_coordinates(coordinates, tolerance_meters):
    coordinates = list(coordinates)
    if len(coordinates) <= 2 or tolerance_meters <= 0:
        return coordinates
    lats = np.array([point.latitude for point in coordinates], dtype=np.float64)
    lons = np.array([point.longitude for point in coordinates], dtype=np.float64)
    scale = math.cos(math.radians(float(np.mean(lats))))
    xs = lons * MILES_PER_DEGREE * scale
    ys = lats * MILES_PER_DEGREE
    keep = douglas_peucker_mask(xs, ys, tolerance_meters / METERS_PER_MILE)
    return [coordinates[index] for index in np.flatnonzero(keep)]


def bounding_box(coordinates):
    lats = [point.latitude for point in coordinates]
    lons = [point.longitude for point in coordinates]
    if not lats:
        return None
    return {"south": min(lats), "west": min(lons), "north": max(lats), "east": max(lons)}
