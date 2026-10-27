"""NGOs our riders deliver to (admin): list, add or edit by hand, and find more with a web search."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import require_roles
from app.core.errors import api_error
from app.db.session import get_db
from app.models import Category, Location, Ngo, User
from app.models.enums import Role
from app.schemas.ngos import NgoIn, NgoOut, NgoSearchIn, NgoSearchOut, NgoUpdate
from app.services import llm, ngo_finder
from app.services.locations import descendant_ids
from app.services.ngos import ngo_out

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
    return [ngo_out(db, n) for n in ngos]


@router.post("", response_model=NgoOut, status_code=status.HTTP_201_CREATED)
def add_ngo(body: NgoIn, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    """An NGO the admin knows (found_by = admin)."""
    if db.get(Location, body.location_id) is None:
        raise api_error(422, "bad_location", "Choose the city from the list")
    n = Ngo(**body.model_dump(exclude={"category_ids"}), found_by="admin", location_approx=False, is_active=True)
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
    return NgoSearchOut(place=r["place"], found=r["found"], added=r["added"], updated=r["updated"], status=r["status"],
                        ngos=[ngo_out(db, n) for n in ngos])
