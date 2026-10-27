"""Rule-based urgency score for food donations (0-100). Only food is time-critical: other donations get
no score (None) and sort after food.

Points (Phase 5 version):
  food type        cooked +35, dry / packed +5
  time since cooked (cooked only)  <1 h +10, 1-3 h +25, 3-6 h +35, 6 h+ +40
  quantity         +0.35 per item, up to +20
  pickup distance  to the nearest NGO that takes cooked food (cooked only):
                   <=2 km +12, <=5 km +8, <=10 km +4, further +0
A cooked meal more than 8 hours old gets a warning reason (0 points) so the admin checks it is still safe.
"""

from datetime import datetime
from typing import Optional

from app.models.enums import FoodType

UNSAFE_AFTER_HOURS = 8


def food_urgency(
    is_food: bool,
    food_type: Optional[FoodType],
    prepared_at: Optional[datetime],
    quantity: int,
    now: datetime,
    ngo_distance_km: Optional[float] = None,
) -> tuple[Optional[int], list[tuple[str, int]]]:
    """Returns (score, reasons). Reasons are shown to the admin, e.g. ("Food type: cooked", 35)."""
    if not is_food:
        return None, []
    reasons: list[tuple[str, int]] = []
    cooked = food_type == FoodType.cooked
    if cooked:
        reasons.append(("Food type: cooked", 35))
        if prepared_at is not None:
            hours = max(0.0, (now - prepared_at).total_seconds() / 3600)
            if hours < 1:
                pts = 10
            elif hours < 3:
                pts = 25
            elif hours < 6:
                pts = 35
            else:
                pts = 40   # very close to unsafe: hand out today or not at all
            reasons.append((f"Time since cooked: {hours:.0f} h" if hours >= 1 else "Time since cooked: under 1 h", pts))
            if hours >= UNSAFE_AFTER_HOURS:
                reasons.append((f"Warning: cooked over {UNSAFE_AFTER_HOURS} h ago, check it is still safe", 0))
    else:
        reasons.append(("Food type: dry / packed", 5))
    qty_pts = min(20, round(quantity * 0.35))
    if qty_pts:
        reasons.append((f"Quantity: {quantity}", qty_pts))
    if cooked:
        if ngo_distance_km is None:
            reasons.append(("No NGO for cooked food known yet", 0))
        else:
            d = ngo_distance_km
            pts = 12 if d <= 2 else 8 if d <= 5 else 4 if d <= 10 else 0
            reasons.append((f"Nearest NGO for cooked food: {d:.1f} km", pts))
    return min(100, sum(p for _, p in reasons)), reasons
