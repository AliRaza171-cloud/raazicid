"""Rule-based urgency score for food donations (0-100). Phase 5 adds pickup distance and tunes the weights.

Only food is time-critical, so other donations get no score (None) and sort after food.
"""

from datetime import datetime
from typing import Optional

from app.models.enums import FoodType


def food_urgency(
    is_food: bool,
    food_type: Optional[FoodType],
    prepared_at: Optional[datetime],
    quantity: int,
    now: datetime,
) -> tuple[Optional[int], list[tuple[str, int]]]:
    """Returns (score, reasons). Reasons are shown to the admin, e.g. ("Food type: cooked", 35)."""
    if not is_food:
        return None, []
    reasons: list[tuple[str, int]] = []
    if food_type == FoodType.cooked:
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
            reasons.append((f"Time since prepared: {hours:.0f} h" if hours >= 1 else "Time since prepared: under 1 h", pts))
    else:
        reasons.append(("Food type: dry / packed", 5))
    qty_pts = min(20, round(quantity * 0.35))
    if qty_pts:
        reasons.append((f"Quantity: {quantity}", qty_pts))
    return min(100, sum(p for _, p in reasons)), reasons
