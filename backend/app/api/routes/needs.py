"""Needs by area (Phase 6): what each province / city / district needs, with reasons and sources."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_roles
from app.core.errors import api_error
from app.db.session import get_db
from app.models import Location, User
from app.models.enums import Role
from app.services.needs import area_needs, recompute

router = APIRouter(tags=["needs"])


@router.get("/needs")
def needs(parent_id: Optional[uuid.UUID] = None, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Provinces (no parent_id) or the places inside one place, each with its needs per category.
    A place shows the highest level found anywhere inside it, with the reasons."""
    if parent_id and db.get(Location, parent_id) is None:
        raise api_error(404, "location_not_found", "Place not found")
    return area_needs(db, parent_id)


@router.post("/admin/needs/recompute")
def recompute_now(_: User = Depends(require_roles(Role.admin)), db: Session = Depends(get_db)):
    return {"rows": recompute(db)}
