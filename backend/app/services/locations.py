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


def ancestor_ids(db: Session, location_id: Optional[uuid.UUID]) -> list[uuid.UUID]:
    """Ids from the place itself up to its province: [area, region, city, province]."""
    ids: list[uuid.UUID] = []
    current = db.get(Location, location_id) if location_id else None
    guard = 0
    while current is not None and guard < 6:
        ids.append(current.id)
        current = db.get(Location, current.parent_id) if current.parent_id else None
        guard += 1
    return ids


def descendant_ids(db: Session, root_id: uuid.UUID) -> list[uuid.UUID]:
    """The place and every place under it (a province gives its cities, regions and areas)."""
    from sqlalchemy import select

    found = [root_id]
    frontier = [root_id]
    for _ in range(4):   # at most province > city > region > area
        if not frontier:
            break
        frontier = list(db.scalars(select(Location.id).where(Location.parent_id.in_(frontier))))
        found.extend(frontier)
    return found
