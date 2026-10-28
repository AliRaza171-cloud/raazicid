"""NGOs our riders deliver to (admin): list, add or edit by hand, find more with a web search or on OpenStreetMap,
and record the checks (confirmed by phone, not on a banned list)."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import require_roles
from app.core.errors import api_error
from app.db.session import get_db
from app.models import Category, Location, Ngo, User
from app.models.enums import Role, SourceKind
from app.schemas.ngos import NgoIn, NgoOsmOut, NgoOut, NgoSearchIn, NgoSearchOut, NgoUpdate
from app.services import llm, ngo_finder, ngo_sources
from app.services.sources import ngo_gaps
from app.services.sources.runner import run_source
from app.services.locations import descendant_ids
from app.services.ngos import ngo_out, need_places, ngos_for_need, search_place

router = APIRouter(prefix="/admin/ngos", tags=["admin: NGOs"])
admin_only = require_roles(Role.admin)


def _categories(db: Session, ids: list[int]) -> list[Category]:
    cats = list(db.scalars(select(Category).where(Category.id.in_(set(ids))))) if ids else []
    if len(cats) != len(set(ids)):
        raise api_error(422, "bad_category", "One of the categories does not exist")
    return cats


def _get(db: Session, ngo_id: uuid.UUID) -> Ngo:
    n = db.get(Ngo, ngo_id)
    if n is None:
        raise api_error(404, "ngo_not_found", "NGO not found")
    return n


@router.get("", response_model=list[NgoOut])
def list_ngos(
    location_id: Optional[uuid.UUID] = Query(None, description="Province, city or district: includes everything under it"),
    category_id: Optional[int] = None,
    q: Optional[str] = None,
    include_hidden: bool = False,
    _: User = Depends(admin_only),
    db: Session = Depends(get_db),
):
    stmt = select(Ngo).order_by(Ngo.name)
    if location_id:
        stmt = stmt.where(Ngo.location_id.in_(descendant_ids(db, location_id)))
    if not include_hidden:
        stmt = stmt.where(Ngo.is_active.is_(True))
    if q and q.strip():
        stmt = stmt.where(Ngo.name.ilike(f"%{q.strip()}%"))
    ngos = list(db.scalars(stmt))
    if category_id:
        ngos = [n for n in ngos if not n.categories or category_id in {c.id for c in n.categories}]
    index = ngo_sources.load_index(db)
    return [ngo_out(db, n, index) for n in ngos]


@router.get("/for-need")
def for_need(location_id: uuid.UUID, category_id: int, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    """NGOs to drop this item at for this place (Needs by area: "NGOs that take blankets here")."""
    if db.get(Location, location_id) is None:
        raise api_error(404, "location_not_found", "Place not found")
    return ngos_for_need(db, location_id, category_id)


@router.get("/by-place")
def by_place(location_id: uuid.UUID, category_id: int, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    """For a province or district: each place inside it that needs this item, with the NGOs nearest to it."""
    if db.get(Location, location_id) is None:
        raise api_error(404, "location_not_found", "Place not found")
    return need_places(db, location_id, category_id)


@router.post("", response_model=NgoOut, status_code=status.HTTP_201_CREATED)
def add_ngo(body: NgoIn, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    """An NGO the admin knows (found_by = admin)."""
    if db.get(Location, body.location_id) is None:
        raise api_error(422, "bad_location", "Choose the city from the list")
    now = datetime.now(timezone.utc)
    n = Ngo(**body.model_dump(exclude={"category_ids", "phone_confirmed", "ban_checked"}), found_by="admin",
            location_approx=False, is_active=True, phone_confirmed_at=now if body.phone_confirmed else None,
            ban_checked_at=now if body.ban_checked else None)
    n.categories = _categories(db, body.category_ids)
    db.add(n)
    db.commit()
    db.refresh(n)
    return ngo_out(db, n)


@router.patch("/{ngo_id}", response_model=NgoOut)
def edit_ngo(ngo_id: uuid.UUID, body: NgoUpdate, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    """Fix details, move the pin (then it is no longer approximate), or hide it (is_active = false)."""
    n = _get(db, ngo_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("location_id") and db.get(Location, data["location_id"]) is None:
        raise api_error(422, "bad_location", "Choose the city from the list")
    if "category_ids" in data:
        n.categories = _categories(db, data.pop("category_ids") or [])
    now = datetime.now(timezone.utc)
    for flag, column in (("phone_confirmed", "phone_confirmed_at"), ("ban_checked", "ban_checked_at")):
        if flag in data:
            value = data.pop(flag)
            if value is not None:
                setattr(n, column, (getattr(n, column) or now) if value else None)
    if data.get("lat") is not None:
        n.location_approx = False
    for key, value in data.items():
        if value is None and key in ("name", "location_id", "address", "lat", "lng", "takes_cooked_food", "is_active"):
            continue   # these cannot be cleared
        setattr(n, key, value)
    db.commit()
    db.refresh(n)
    return ngo_out(db, n)


@router.post("/search", response_model=NgoSearchOut)
def search_web(body: NgoSearchIn, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    """Search the web for NGOs in the city of `location_id` that take donated goods, and save them (1-3 minutes)."""
    if db.get(Location, body.location_id) is None:
        raise api_error(404, "location_not_found", "Place not found")
    if not llm.available():
        raise api_error(422, "ai_not_set_up", llm.not_set_up())
    try:
        r = ngo_finder.find_and_save(db, body.location_id, body.category_id)
    except llm.LLMError as e:
        raise api_error(502, "search_failed", str(e))
    inside = descendant_ids(db, r["place_id"])
    ngos = db.scalars(select(Ngo).where(Ngo.location_id.in_(inside), Ngo.is_active.is_(True)).order_by(Ngo.name))
    index = ngo_sources.load_index(db)
    return NgoSearchOut(place=r["place"], found=r["found"], added=r["added"], updated=r["updated"], status=r["status"],
                        ngos=[ngo_out(db, n, index) for n in ngos])


@router.post("/osm", response_model=NgoOsmOut)
def from_openstreetmap(body: NgoSearchIn, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    """NGO, charity and social-facility offices on OpenStreetMap in the city of `location_id` (free, no AI credit).
    New ones are added to call (what they take is not known yet); NGOs we knew only by city get their office pin."""
    place = search_place(db, body.location_id)
    if place is None:
        raise api_error(404, "location_not_found", "Place not found")
    centre = ngo_gaps.ensure_centre(db, place)   # districts from HDX get their map centre from OpenStreetMap once
    if centre is None:
        raise api_error(422, "no_map_centre", f"We have no map position for {place.name}")
    place_id, place_name, (lat, lng), radius = place.id, place.name, centre, ngo_sources.radius_for(place.level)
    db.commit()   # no transaction open while waiting for Overpass
    offices = ngo_sources.osm_offices(lat, lng, radius)
    inside = descendant_ids(db, place_id)
    known = list(db.scalars(select(Ngo).where(Ngo.location_id.in_(inside))))
    added = located = 0
    for o in offices:
        n = next((k for k in known if ngo_sources.same_org(k.name, o["name"])), None)
        if n is not None:
            if n.location_approx:
                n.lat, n.lng, n.location_approx = o["lat"], o["lng"], False
                if o["address"] and "address not found" in n.address:
                    n.address = o["address"]
                located += 1
            if not n.phone and o["phone"]:
                n.phone = o["phone"]
            continue
        n = Ngo(name=o["name"], location_id=place_id, address=o["address"] or f"{place_name} (see the map pin)",
                lat=o["lat"], lng=o["lng"], location_approx=False, phone=o["phone"], website=o["website"],
                about=f"{o['kind'].capitalize()} on OpenStreetMap", source_url=o["url"], found_by="openstreetmap",
                takes_cooked_food=False, is_active=True)
        db.add(n)
        known.append(n)
        added += 1
    db.commit()
    status = (f"OpenStreetMap has {len(offices)} NGO or charity offices around {place_name}: {added} new, "
              f"{located} we knew now have their office on the map. Call new ones to ask what they take.") if offices else \
        f"OpenStreetMap has no NGO or charity offices tagged around {place_name} (or it is busy: try again in a minute)."
    index = ngo_sources.load_index(db)
    ngos = db.scalars(select(Ngo).where(Ngo.location_id.in_(inside), Ngo.is_active.is_(True)).order_by(Ngo.name))
    return NgoOsmOut(place=place_name, found=len(offices), added=added, located=located, status=status,
                     ngos=[ngo_out(db, n, index) for n in ngos])


class FillGapsIn(BaseModel):
    location_id: Optional[uuid.UUID] = None   # only places in need inside this one (all Pakistan if empty)
    use_ai: bool = True                       # also web search (AI credit) where the free sources found nothing
    category_id: Optional[int] = None         # with location_id: NGOs for this item there, whatever the need level


@router.post("/fill-gaps")
def fill_gaps(body: FillGapsIn, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    """Find NGOs for the places in high or urgent need that have none nearby: OpenStreetMap, then OCHA 3W, then a web
    search (at most NGO_AI_SEARCHES_PER_RUN). Takes from seconds to a few minutes."""
    if body.location_id and db.get(Location, body.location_id) is None:
        raise api_error(404, "location_not_found", "Place not found")
    ok, status_line = run_source(db, SourceKind.ngo_finder, {"location_id": body.location_id, "use_ai": body.use_ai,
                                                             "category_id": body.category_id})
    return {"ok": ok, "status": status_line}
