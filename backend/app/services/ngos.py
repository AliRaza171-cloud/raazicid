"""NGOs our riders deliver to: listing, which NGO can take a donation, and the city a search covers."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Appeal, Category, DisasterAlert, Donation, Location, Ngo
from app.models.enums import AlertStatus, LocationLevel
from app.models.enums import DonationStatus as S
from app.schemas.donations import CategoryRef, NgoOption, NgoRef
from app.schemas.ngos import NgoOut, WorksIn
from app.services.geo import distance_km
from app.services.locations import ancestor_ids, coords_problem, descendant_ids, location_path
from app.services.ngo_sources import Presence, load_index, works_for
from app.services.relief import alert_slugs

ALERT_DAYS = 30


def items_30d(db: Session, ngo_id: uuid.UUID) -> int:
    since = datetime.now(timezone.utc) - timedelta(days=30)
    return db.scalar(select(func.count()).select_from(Donation).where(
        Donation.ngo_id == ngo_id, Donation.created_at >= since, Donation.status.notin_([S.rejected, S.cancelled]))) or 0


def ngo_out(db: Session, n: Ngo, index: Optional[list[Presence]] = None) -> NgoOut:
    """`index` = load_index(db), loaded once when listing many NGOs."""
    works = works_for(n.name, index if index is not None else load_index(db))
    return NgoOut(
        works=[WorksIn(place=place, sectors=sectors) for place, sectors in works.places.items()], works_text=works.text(),
        phone_confirmed_at=n.phone_confirmed_at, ban_checked_at=n.ban_checked_at, registration=n.registration,
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


def disaster_areas(db: Session, d: Donation) -> list[tuple[str, set]]:
    """(alert title, place ids) for the disasters this donation can help: the alert of the appeal it answers, else
    every active alert that needs this kind of item. Province-wide places are left out (too broad)."""
    since = datetime.now(timezone.utc) - timedelta(days=ALERT_DAYS)
    alerts = list(db.scalars(select(DisasterAlert).where(
        DisasterAlert.status.in_([AlertStatus.confirmed, AlertStatus.unconfirmed]), DisasterAlert.created_at >= since)))
    appeal = db.get(Appeal, d.appeal_id) if d.appeal_id else None
    if appeal is not None and appeal.alert_id:
        alerts = [a for a in alerts if a.id == appeal.alert_id]
    else:
        cat = db.get(Category, d.category_id)
        today = datetime.now(timezone.utc).date()
        alerts = [a for a in alerts if cat and cat.slug in alert_slugs(a.type, today, (a.started_at or a.created_at).date())]
    provinces = set(db.scalars(select(Location.id).where(Location.level == LocationLevel.province)))
    out = []
    for a in alerts:
        ids: set = set()
        for loc in a.locations:
            ids |= set(ancestor_ids(db, loc.id)) | set(descendant_ids(db, loc.id))
        ids -= provinces
        if ids:
            out.append((a.title, ids))
    return out


def ngo_options(db: Session, d: Donation, limit: int = 12) -> list[NgoOption]:
    """NGOs that can take the donation. Order: reachable ones (not another province) first; among them NGOs working
    where a disaster needs this item (OCHA 3W, or an office there), then NGOs an admin has checked, then same area,
    region, city, province, then by distance."""
    index = load_index(db)
    disasters = disaster_areas(db, d)
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
        works = works_for(n.name, index)
        disaster = None
        for title, ids in disasters:
            if works.location_ids & ids:
                disaster = f"Works where it is needed: {title}"
                break
            if n.location_id in ids:
                disaster = f"Office in the disaster area: {title}"
                break
        options.append(NgoOption(
            works_text=works.text(), disaster=disaster, phone_confirmed=n.phone_confirmed_at is not None,
            ban_checked=n.ban_checked_at is not None, registration=n.registration,
            id=n.id, name=n.name, address=n.address, location_path=location_path(db, n.location_id),
            distance_km=round(distance_km(d.pickup_lat, d.pickup_lng, n.lat, n.lng), 1), match=best, phone=n.phone,
            takes_cooked_food=n.takes_cooked_food, location_approx=n.location_approx, found_by=n.found_by,
            source_url=n.source_url, items_30d=items_30d(db, n.id),
        ))
    order = {"same_area": 0, "same_region": 1, "same_city": 2, "same_province": 3, "other": 4}
    options.sort(key=lambda o: (o.match == "other", o.disaster is None, not (o.phone_confirmed and o.ban_checked),
                                order[o.match], o.distance_km))
    return options[:limit]


def nearest_food_ngo_km(db: Session, lat: float, lng: float) -> Optional[float]:
    """Distance to the nearest NGO that takes cooked food (food urgency)."""
    best = None
    for n in db.scalars(select(Ngo).where(Ngo.takes_cooked_food.is_(True), Ngo.is_active.is_(True))):
        km = distance_km(lat, lng, n.lat, n.lng)
        best = km if best is None or km < best else best
    return best


def ngos_for_need(db: Session, location_id: uuid.UUID, category_id: int, limit: int = 8) -> list[dict]:
    """NGOs to drop this item at for this place: offices in the place or within 30 km that take the item, and NGOs
    OCHA 3W says work there. Order: reachable offices first, then working there (3W), then those that list the item
    (not just "everything"), then checked ones, then nearest."""
    loc = db.get(Location, location_id)
    if loc is None:
        return []
    inside = set(descendant_ids(db, location_id))
    chain = [db.get(Location, i) for i in ancestor_ids(db, location_id)]
    here = inside | {l.id for l in chain if l is not None and l.level != LocationLevel.province}
    centre = next(((l.lat, l.lng) for l in chain if l is not None and l.lat is not None and l.level != LocationLevel.province), None)
    index = load_index(db)
    out = []
    for n in db.scalars(select(Ngo).where(Ngo.is_active.is_(True))):
        listed = {c.id for c in n.categories}
        if listed and category_id not in listed:
            continue
        works = works_for(n.name, index)
        active = bool(works.location_ids & here)
        dist = None if (centre is None or n.location_approx) else round(distance_km(centre[0], centre[1], n.lat, n.lng), 1)
        reachable = n.location_id in inside or (dist is not None and dist <= 30) or (n.location_approx and n.location_id in here)
        if not (reachable or active):
            continue
        out.append({"id": str(n.id), "name": n.name, "address": n.address, "phone": n.phone,
                    "city": location_path(db, n.location_id)[-1], "distance_km": dist, "reachable": reachable,
                    "active_here": active, "works_text": works.text(), "takes_listed": bool(listed),
                    "checked": n.phone_confirmed_at is not None and n.ban_checked_at is not None,
                    "location_approx": n.location_approx, "lat": n.lat, "lng": n.lng, "found_by": n.found_by})
    out.sort(key=lambda x: (not x["reachable"], not x["active_here"], not x["takes_listed"], not x["checked"],
                            x["distance_km"] if x["distance_km"] is not None else 999))
    return out[:limit]
