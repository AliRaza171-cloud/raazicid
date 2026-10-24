"""Small geography helpers (no map API needed)."""

from math import asin, cos, radians, sin, sqrt

# Rough box around Pakistan with a margin. Catches swapped lat/lng and phones reporting 0,0.
PK_LAT = (23.0, 37.5)
PK_LNG = (60.5, 77.9)


def in_pakistan(lat: float, lng: float) -> bool:
    return PK_LAT[0] <= lat <= PK_LAT[1] and PK_LNG[0] <= lng <= PK_LNG[1]


def distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Straight-line distance (haversine). Road distance comes with Google Maps in Phase 4."""
    lat1, lng1, lat2, lng2 = map(radians, (lat1, lng1, lat2, lng2))
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lng2 - lng1) / 2) ** 2
    return 6371.0 * 2 * asin(sqrt(a))
