BOUNDING_BOXES = (
    (24.396308, -125.000000, 49.384358, -66.934570),
    (51.214183, -179.148909, 71.538800, -129.979511),
    (18.910361, -160.247100, 22.235500, -154.806773),
)


def is_within_usa(coordinate):
    for south, west, north, east in BOUNDING_BOXES:
        if south <= coordinate.latitude <= north and west <= coordinate.longitude <= east:
            return True
    return False
