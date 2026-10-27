"""NGOs our riders deliver to: listing, which NGO can take a donation, and the city a search covers."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Donation, Location, Ngo
from app.models.enums import DonationStatus as S
from app.models.enums import LocationLevel
from app.schemas.donations import CategoryRef, NgoOption, NgoRef
from app.schemas.ngos import NgoOut
from app.services.geo import distance_km
from app.services.locations import ancestor_ids, coords_problem, location_path


def items_30d(db: Session, ngo_id: uuid.UUID) -> int:
    since = datetime.now(timezone.utc) - timedelta(days=30)
    return db.scalar(select(func.count()).select_from(Donation).where(
        Donation.ngo_id == ngo_id, Donation.created_at >= since, Donation.status.notin_([S.rejected, S.cancelled]))) or 0


def ngo_out(db: Session, n: Ngo) -> NgoOut:
    return NgoOut(
        id=n.id, name=n.name, location_id=n.location_id, location_path=location_path(db, n.location_id), address=n.address,
        lat=n.lat, lng=n.lng, location_approx=n.location_approx, phone=n.phone, website=n.website, about=n.about,
        takes_cooked_food=n.takes_cooked_food, source_url=n.source_url, found_by=n.found_by, is_active=n.is_active,
        categories=[CategoryRef(id=c.id, name=c.name) for c in sorted(n.categories, key=lambda c: c.id)],
        items_30d=items_30d(db, n.id), created_at=n.created_at,
        place_warning=None if n.location_approx else coords_problem(db, n.location_id, n.lat, n.lng),
    )


def ngo_ref(db: Session, n: Optional[Ngo]) -> Optional[NgoRef]:
    if n is None:
        return None
    return NgoRef(id=n.id, name=n.name, address=n.address, location_path=location_path(db, n.location_id), lat=n.lat,
                  lng=n.lng, phone=n.phone, location_approx=n.location_approx)


def ngo_takes(n: Ngo, d: Donation) -> Optional[str]:
    """None if the NGO can take this donation, otherwise the reason it cannot."""
    if not n.is_active:
        return "This NGO is hidden"
    if n.categories and d.category_id not in {c.id for c in n.categories}:
        return "This NGO does not take this category"
    if d.is_food and d.food_type is not None and d.food_type.value == "cooked" and not n.takes_cooked_food:
        return "This NGO does not take cooked food"
    return None


def search_place(db: Session, location_id: Optional[uuid.UUID]) -> Optional[Location]:
    """The city (or district) to search NGOs in: a city above the place, else the district, else the place."""
    chain = [db.get(Location, i) for i in ancestor_ids(db, location_id)]
    chain = [l for l in chain if l is not None]
    for level in (LocationLevel.city, LocationLevel.region):
        hit = next((l for l in chain if l.level == level), None)
        if hit is not None:
            return hit
    return chain[0] if chain else None


def ngo_options(db: Session, d: Donation, limit: int = 12) -> list[NgoOption]:
    """NGOs that can take the donation: same area first, then region, city, province, then by distance."""
    pickup_chain = ancestor_ids(db, d.pickup_location_id)   # [area, region, city, province]
    levels = {loc_id: i for i, loc_id in enumerate(pickup_chain)}
    names = ["same_area", "same_region", "same_city", "same_province"]
    offset = 4 - len(pickup_chain) if pickup_chain else 0
    options = []
    for n in db.scalars(select(Ngo).where(Ngo.is_active.is_(True))):
        if ngo_takes(n, d) is not None:
            continue
        best = "other"
        for loc_id in ancestor_ids(db, n.location_id):
            if loc_id in levels:
                idx = levels[loc_id] + offset
                best = names[idx] if idx < len(names) else "other"
                break
        options.append(NgoOption(
            id=n.id, name=n.name, address=n.address, location_path=location_path(db, n.location_id),
            distance_km=round(distance_km(d.pickup_lat, d.pickup_lng, n.lat, n.lng), 1), match=best, phone=n.phone,
            takes_cooked_food=n.takes_cooked_food, location_approx=n.location_approx, found_by=n.found_by,
            source_url=n.source_url, items_30d=items_30d(db, n.id),
        ))
    order = {"same_area": 0, "same_region": 1, "same_city": 2, "same_province": 3, "other": 4}
    options.sort(key=lambda o: (order[o.match], o.distance_km))
    return options[:limit]


def nearest_food_ngo_km(db: Session, lat: float, lng: float) -> Optional[float]:
    """Distance to the nearest NGO that takes cooked food (food urgency)."""
    best = None
    for n in db.scalars(select(Ngo).where(Ngo.takes_cooked_food.is_(True), Ngo.is_active.is_(True))):
        km = distance_km(lat, lng, n.lat, n.lng)
        best = km if best is None or km < best else best
    return best
