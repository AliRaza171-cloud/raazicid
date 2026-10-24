import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Location


def location_path(db: Session, location_id: Optional[uuid.UUID]) -> list[str]:
    """Names from province down to the given place: ['Sindh', 'Karachi', 'Karachi East', 'Gulshan-e-Iqbal']."""
    names: list[str] = []
    current = db.get(Location, location_id) if location_id else None
    guard = 0
    while current is not None and guard < 6:
        names.append(current.name)
        current = db.get(Location, current.parent_id) if current.parent_id else None
        guard += 1
    return list(reversed(names))
