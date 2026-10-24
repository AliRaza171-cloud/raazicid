"""Rider recommendation score (Phase 5). Rule-based and explainable: every point has a reason.

Score 0-100 =
  distance to pickup  up to 40  (live GPS from the last 2 hours; otherwise the rider's home area)
  current load        up to 20  (fewer active jobs is better)
  availability        up to 15  (rider switched "Available" on)
  rating              up to 15  (average donor rating; new riders get a neutral 10)
  vehicle fit         up to 10  (big loads need a pickup or rickshaw; small ones suit a motorbike)
"""

from dataclasses import dataclass
from typing import Optional

# Categories whose items are bulky even in small numbers
BULKY = {"blankets", "household", "mobility_aids", "emergency_relief"}
AREA_POINTS = {"same_area": 30, "same_region": 24, "same_city": 16, "same_province": 6, "other": 0}
AREA_TEXT = {"same_area": "same area", "same_region": "same region", "same_city": "same city",
             "same_province": "same province", "other": "another province"}


@dataclass
class RiderFacts:
    distance_km: Optional[float]   # None = no fresh GPS
    area_match: str                # same_area | same_region | same_city | same_province | other
    active_jobs: int
    is_available: bool
    rating_avg: Optional[float]
    vehicle: str                   # motorbike | rickshaw | pickup


def load_size(quantity: int, category_slug: str) -> str:
    if quantity > 20 or (category_slug in BULKY and quantity > 5):
        return "large"
    if quantity > 5 or category_slug in BULKY:
        return "medium"
    return "small"


VEHICLE_FIT = {
    "large": {"pickup": 10, "rickshaw": 6, "motorbike": 1},
    "medium": {"pickup": 8, "rickshaw": 10, "motorbike": 6},
    "small": {"pickup": 5, "rickshaw": 8, "motorbike": 10},
}


def score_rider(f: RiderFacts, quantity: int, category_slug: str) -> tuple[int, list[tuple[str, int]]]:
    reasons: list[tuple[str, int]] = []

    if f.distance_km is not None:
        pts = round(max(0.0, 40 * (1 - f.distance_km / 15)))   # 0 km -> 40, 15 km or more -> 0
        reasons.append((f"{f.distance_km:.1f} km from pickup (live GPS)", pts))
    else:
        pts = AREA_POINTS[f.area_match]
        reasons.append((f"Lives in the {AREA_TEXT[f.area_match]}", pts))

    load = {0: 20, 1: 12, 2: 5}.get(f.active_jobs, 0)
    reasons.append(("No active jobs" if f.active_jobs == 0 else f"{f.active_jobs} active job{'s' if f.active_jobs > 1 else ''}", load))

    reasons.append(("Available now" if f.is_available else "Off duty", 15 if f.is_available else 0))

    if f.rating_avg is None:
        reasons.append(("New rider, no rating yet", 10))
    else:
        reasons.append((f"Rating {f.rating_avg:.1f} / 5", round(15 * max(0.0, min(5.0, f.rating_avg)) / 5)))

    size = load_size(quantity, category_slug)
    fit = VEHICLE_FIT[size][f.vehicle]
    reasons.append((f"{f.vehicle.title()} for a {size} load", fit))

    return min(100, sum(p for _, p in reasons)), reasons
