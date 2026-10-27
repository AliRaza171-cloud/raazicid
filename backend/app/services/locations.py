import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Location
from app.models.enums import LocationLevel
from app.services.geo import distance_km

# How far a pin may be from the centre of the place it is filed under before we say the coordinates look wrong
NEAR_KM = {LocationLevel.city: 60, LocationLevel.region: 30, LocationLevel.area: 30}


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


def centre(db: Session, location_id: Optional[uuid.UUID]) -> Optional[Location]:
    """The place itself, or the nearest larger place, that has map coordinates (provinces are too big to count)."""
    for loc_id in ancestor_ids(db, location_id):
        loc = db.get(Location, loc_id)
        if loc is not None and loc.lat is not None and loc.level in NEAR_KM:
            return loc
    return None


def nearest_city(db: Session, lat: float, lng: float) -> Optional[tuple[Location, float]]:
    cities = db.scalars(select(Location).where(Location.level == LocationLevel.city, Location.lat.is_not(None)))
    best = min(((c, distance_km(lat, lng, c.lat, c.lng)) for c in cities), key=lambda x: x[1], default=None)
    return best


def coords_problem(db: Session, location_id: uuid.UUID, lat: float, lng: float) -> Optional[str]:
    """A plain sentence when the coordinates are far from the place chosen (e.g. Karachi numbers for a Hyderabad
    point), else None."""
    place = db.get(Location, location_id)
    if place is None:
        return None
    near = nearest_city(db, lat, lng)
    where = f" They are near {near[0].name}." if near and near[1] <= 40 else ""
    c = centre(db, location_id)
    if c is not None:
        d = distance_km(lat, lng, c.lat, c.lng)
        if d > NEAR_KM[c.level]:
            if near and near[0].id == c.id:
                where = ""
            filed = "" if c.id == place.id else f" (it is filed under {place.name})"
            return f"The coordinates are about {round(d)} km from {c.name}{filed}.{where}"
        return None
    # No coordinates for the place: at least check the province of the nearest city
    if near and near[1] <= 40:
        chain = ancestor_ids(db, location_id)
        city_province = ancestor_ids(db, near[0].id)[-1]
        if chain and chain[-1] != city_province:
            return f"The coordinates are near {near[0].name}, which is in another province than {place.name}."
    return None
