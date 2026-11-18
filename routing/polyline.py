from .types import Coordinate


def decode_polyline(encoded, precision=5):
    factor = 10**precision
    coordinates = []
    index = 0
    latitude = 0
    longitude = 0
    length = len(encoded)
    while index < length:
        deltas = []
        for _ in range(2):
            result = 0
            shift = 0
            while True:
                if index >= length:
                    raise ValueError("Truncated polyline string")
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        latitude += deltas[0]
        longitude += deltas[1]
        coordinates.append(Coordinate(latitude=latitude / factor, longitude=longitude / factor))
    return coordinates
