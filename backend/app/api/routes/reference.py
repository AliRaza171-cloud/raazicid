"""Read-only reference data both apps need from day one: categories and the location tree."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Category, Location
from app.models.enums import LocationLevel

router = APIRouter(tags=["reference"])


class CategoryOut(BaseModel):
    id: int
    slug: str
    name: str
    is_perishable: bool


class LocationOut(BaseModel):
    id: uuid.UUID
    name: str
    level: LocationLevel
    parent_id: Optional[uuid.UUID]
    lat: Optional[float] = None
    lng: Optional[float] = None


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)):
    rows = db.scalars(select(Category).order_by(Category.id)).all()
    return [CategoryOut(id=c.id, slug=c.slug, name=c.name, is_perishable=c.is_perishable) for c in rows]


@router.get("/locations", response_model=list[LocationOut])
def list_locations(
    parent_id: Optional[uuid.UUID] = Query(None, description="Children of this place. Leave empty for provinces."),
    db: Session = Depends(get_db),
):
    """Used by the cascading dropdowns: Province > City > Region > Area."""
    stmt = select(Location).order_by(Location.name)
    stmt = stmt.where(Location.parent_id == parent_id) if parent_id else stmt.where(
        Location.level == LocationLevel.province
    )
    return [LocationOut(id=l.id, name=l.name, level=l.level, parent_id=l.parent_id, lat=l.lat, lng=l.lng) for l in db.scalars(stmt)]
