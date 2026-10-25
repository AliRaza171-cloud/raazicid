"""Find Pakistani places in text (reports, news, GDACS) and the nearest known place to a GPS point.

Pure functions work on a small Place list, so they can be tested without a database; `load_places` builds
that list from the locations table.
"""

import re
import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Location
from app.seed.data import PLACE_ALIASES
from app.services.geo import distance_km

# Short words that are also place names would match too often; only accept them as whole capitalised words.
AMBIGUOUS = {"GB", "KP", "ICT", "Sind", "Swat"}


@dataclass(frozen=True)
class Place:
    id: uuid.UUID
    name: str
    level: str
    parent_id: Optional[uuid.UUID]
    lat: Optional[float]
    lng: Optional[float]


def load_places(db: Session) -> list[Place]:
    return [Place(l.id, l.name, l.level.value, l.parent_id, l.lat, l.lng) for l in db.scalars(select(Location))]


def _ancestors(places: dict[uuid.UUID, Place], pid: uuid.UUID) -> set[uuid.UUID]:
    out, cur, guard = set(), places.get(pid), 0
    while cur and cur.parent_id and guard < 6:
        out.add(cur.parent_id)
        cur = places.get(cur.parent_id)
        guard += 1
    return out


def find_places(text: str, places: list[Place]) -> list[Place]:
    """Places named in the text, most specific only (a district drops its province from the result)."""
    if not text:
        return []
    by_id = {p.id: p for p in places}
    names: list[tuple[str, Place]] = []
    for p in places:
        names.append((p.name, p))
        for alias in PLACE_ALIASES.get(p.name, []):
            names.append((alias, p))
    # Longest names first, so "Karachi South" wins over "Karachi"
    names.sort(key=lambda n: -len(n[0]))
    found: dict[uuid.UUID, Place] = {}
    taken: list[tuple[int, int]] = []
    for name, p in names:
        flags = 0 if name in AMBIGUOUS else re.IGNORECASE
        for m in re.finditer(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text, flags):
            if any(m.start() < b and a < m.end() for a, b in taken):
                continue   # part of a longer name already found
            taken.append((m.start(), m.end()))
            found[p.id] = p
    covered = set()
    for pid in found:
        covered |= _ancestors(by_id, pid)
    return [p for pid, p in found.items() if pid not in covered]


def nearest_place(lat: float, lng: float, places: list[Place], max_km: float = 400) -> tuple[Optional[Place], Optional[float]]:
    """Closest province or city with known coordinates (used for GDACS events)."""
    best, best_km = None, None
    for p in places:
        if p.lat is None or p.level not in ("province", "city"):
            continue
        km = distance_km(lat, lng, p.lat, p.lng)
        # Cities are more useful than province centres, so give them a small head start
        score = km - (25 if p.level == "city" else 0)
        if best is None or score < best_km - (25 if best.level == "city" else 0):
            best, best_km = p, km
    if best is None or best_km > max_km:
        return None, None
    return best, best_km


def province_of(place: Place, places: list[Place]) -> Place:
    by_id = {p.id: p for p in places}
    cur, guard = place, 0
    while cur.parent_id and guard < 6:
        cur = by_id[cur.parent_id]
        guard += 1
    return cur
