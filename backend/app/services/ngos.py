"""NGOs our riders deliver to: listing, which NGO can take a donation, and the city a search covers."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Appeal, Category, DisasterAlert, Donation, Location, NeedLevel, Ngo
from app.models.enums import AlertStatus, LocationLevel
from app.models.enums import DonationStatus as S
from app.schemas.donations import CategoryRef, NgoOption, NgoRef
from app.schemas.ngos import NgoOut, WorksIn
from app.services.geo import distance_km
from app.services.locations import ancestor_ids, coords_problem, descendant_ids, location_path
from app.services.ngo_sources import Presence, Works, load_index, same_org, takes_goods, works_for
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


def _need_item(db: Session, n: Ngo, works: Works, dist: Optional[float], reachable: bool, active: bool) -> dict:
    listed = bool(n.categories)
    return {"website": n.website, "about": n.about, "registration": n.registration,
            "takes": [c.name for c in sorted(n.categories, key=lambda c: c.id)],
            "phone_confirmed": n.phone_confirmed_at is not None, "ban_checked": n.ban_checked_at is not None,
            "id": str(n.id), "name": n.name, "address": n.address, "phone": n.phone,
            "city": location_path(db, n.location_id)[-1], "distance_km": dist, "reachable": reachable,
            "active_here": active, "works_text": works.text(), "takes_listed": listed,
            "checked": n.phone_confirmed_at is not None and n.ban_checked_at is not None,
            "location_approx": n.location_approx, "lat": n.lat, "lng": n.lng, "found_by": n.found_by}


def _need_order(x: dict) -> tuple:
    return (not x["reachable"], not x["active_here"], not x["takes_listed"], not x["checked"],
            x["distance_km"] if x["distance_km"] is not None else 999)


def ngos_taking(db: Session, category_id: int) -> list[tuple[Ngo, Works]]:
    """Active NGOs that take this item (or everything) and can take donated goods at all."""
    index = load_index(db)
    out = []
    for n in db.scalars(select(Ngo).where(Ngo.is_active.is_(True))):
        listed = {c.id for c in n.categories}
        if (listed and category_id not in listed) or not takes_goods(n.name, n.about, n.found_by):
            continue
        out.append((n, works_for(n.name, index)))
    return out


def _centre(db: Session, location_id: uuid.UUID) -> Optional[tuple[float, float]]:
    chain = [db.get(Location, i) for i in ancestor_ids(db, location_id)]
    return next(((l.lat, l.lng) for l in chain if l is not None and l.lat is not None and l.level != LocationLevel.province), None)


def served_ids(db: Session, location_id: uuid.UUID) -> set:
    """Where an NGO must be filed to count as "in" a place: the place, anything inside it, and the town or city it is
    part of (Karachi NGOs serve Lyari and Karachi South), never just the same province."""
    chain = [db.get(Location, i) for i in ancestor_ids(db, location_id)]
    return set(descendant_ids(db, location_id)) | {l.id for l in chain if l is not None and l.level != LocationLevel.province}


def _for_one(db: Session, location_id: uuid.UUID, cands: list[tuple[Ngo, Works]]) -> list[dict]:
    """NGOs in the place (filed there, or OCHA 3W says they work there), nearest first. No distance limit: a place
    counts as covered only by NGOs in it; otherwise the nearest town with NGOs is used (need_places)."""
    here = served_ids(db, location_id)
    centre = _centre(db, location_id)
    out = []
    for n, works in cands:
        active = bool(works.location_ids & here)
        reachable = n.location_id in here
        if reachable or active:
            dist = None if (centre is None or n.location_approx) else round(distance_km(centre[0], centre[1], n.lat, n.lng), 1)
            out.append(_need_item(db, n, works, dist, reachable, active))
    return sorted(out, key=_need_order)


def ngos_for_need(db: Session, location_id: uuid.UUID, category_id: int, limit: int = 15) -> list[dict]:
    """NGOs to drop this item at for this place: NGOs in the place that take the item, and NGOs OCHA 3W says work
    there. Order: offices in the place first, then working there (3W), then those that list the item (not just
    "everything"), then checked ones, then nearest."""
    if db.get(Location, location_id) is None:
        return []
    return _for_one(db, location_id, ngos_taking(db, category_id))[:limit]


def towns_with_ngos(db: Session, cands: list[tuple[Ngo, Works]]) -> dict[uuid.UUID, list[tuple[Ngo, Works]]]:
    """The town (city, else district) each NGO is in, with the NGOs there."""
    out: dict[uuid.UUID, list[tuple[Ngo, Works]]] = {}
    for n, w in cands:
        town = search_place(db, n.location_id)
        if town is not None and town.level != LocationLevel.province:
            out.setdefault(town.id, []).append((n, w))
    return out


def nearest_town(db: Session, location_id: uuid.UUID, towns: dict[uuid.UUID, list]) -> Optional[tuple[uuid.UUID, float]]:
    """The nearest other town or city that has NGOs (Jamshoro -> Hyderabad), by the distance between their centres."""
    centre = _centre(db, location_id)
    if centre is None:
        return None
    here = served_ids(db, location_id)
    best = None
    for tid in towns:
        if tid in here:
            continue
        c = _centre(db, tid)
        if c is None:
            continue
        km = distance_km(centre[0], centre[1], c[0], c[1])
        if best is None or km < best[1]:
            best = (tid, km)
    return best


def need_places(db: Session, location_id: uuid.UUID, category_id: int, max_places: int = 20, per_place: int = 3) -> list[dict]:
    """For a province (or any place), each town or district inside it that needs the item, highest need first, with
    the NGOs in that place to drop it at. A place with none gets the nearest town that has NGOs taking the item
    (Jamshoro -> Hyderabad) and its NGOs, with the distance, so riders know where to go."""
    loc = db.get(Location, location_id)
    if loc is None:
        return []
    inside = descendant_ids(db, location_id)
    levels = list(db.scalars(select(NeedLevel).where(NeedLevel.location_id.in_(inside), NeedLevel.category_id == category_id,
                                                     NeedLevel.level >= 1).order_by(NeedLevel.score.desc())))
    places: dict[uuid.UUID, int] = {}
    for nl in levels:   # areas count under their town, so one row per town or district
        p = search_place(db, nl.location_id)
        if p is not None and p.level != LocationLevel.province:
            places.setdefault(p.id, nl.level)
    if not places and loc.level != LocationLevel.province:
        places[loc.id] = 0
    cands = ngos_taking(db, category_id)
    towns = towns_with_ngos(db, cands)
    chosen = list(places.items())[:max_places]
    missing = [pid for pid, _ in chosen if _centre(db, pid) is None][:2] if settings.MAP_PLACES_ON_VIEW else []
    if missing:   # districts added from HDX have no map position yet: look up a couple per visit (OpenStreetMap)
        from app.services.sources.ngo_gaps import ensure_centre
        for pid in missing:
            ensure_centre(db, db.get(Location, pid))
    out = []
    for pid, level in chosen:
        found = _for_one(db, pid, cands)
        own = _distinct([x for x in found if x["reachable"]])
        # Working in the place by OCHA 3W, but their office there is not known (it is filed in another city)
        elsewhere = [x for x in _distinct([x for x in found if not x["reachable"]])
                     if not any(same_org(x["name"], o["name"]) for o in own)]
        fallback = None
        if not own:
            hit = nearest_town(db, pid, towns)
            if hit is not None:
                tid, km = hit
                centre = _centre(db, pid)
                items = [_need_item(db, n, w, None if n.location_approx else round(distance_km(centre[0], centre[1], n.lat, n.lng), 1),
                                    False, False) for n, w in towns[tid]]
                items = _distinct(sorted(items, key=_need_order))
                fallback = {"town_id": str(tid), "town": location_path(db, tid)[-1], "km": round(km),
                            "ngos": items[:per_place], "more": max(0, len(items) - per_place)}
        centre = _centre(db, pid)
        out.append({"place_id": str(pid), "place": location_path(db, pid)[-1], "path": location_path(db, pid), "level": level,
                    "has_position": centre is not None, "lat": centre[0] if centre else None, "lng": centre[1] if centre else None,
                    "ngos": own[:per_place], "more": max(0, len(own) - per_place),
                    "works_here": [{"id": x["id"], "name": x["name"], "city": x["city"], "phone": x["phone"]} for x in elsewhere[:6]],
                    "fallback": fallback})
    return out


def _distinct(items: list[dict]) -> list[dict]:
    """One row per organisation: the same NGO saved in several cities (from 3W) shows once, the best-placed copy."""
    out: list[dict] = []
    for x in items:
        if not any(same_org(x["name"], o["name"]) for o in out):
            out.append(x)
    return out
