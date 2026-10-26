"""Needs by area (Phase 6): what each province / city / district needs, with reasons and sources."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_roles
from app.core.errors import api_error
from app.db.session import get_db
from app.models import Location, User
from app.models.enums import LocationLevel, Role, SourceKind
from app.services import llm
from app.services.needs import area_needs, recompute
from app.services.sources.runner import run_source

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


class ScanIn(BaseModel):
    location_id: Optional[uuid.UUID] = None   # a province, or empty for all Pakistan


@router.post("/admin/needs/ai-scan")
def ai_scan(body: ScanIn, _: User = Depends(require_roles(Role.admin)), db: Session = Depends(get_db)):
    """The AI searches the last 90 days of news, UN and NGO reports for current needs (takes 1-4 minutes, a few
    web searches). Replaces the previous scan of the same province and refreshes the need levels."""
    if not llm.available():
        raise api_error(422, "ai_not_set_up", llm.not_set_up())
    if body.location_id:
        loc = db.get(Location, body.location_id)
        if loc is None or loc.level != LocationLevel.province:
            raise api_error(422, "bad_province", "Choose a province, or leave it empty for all Pakistan")
    ok, status = run_source(db, SourceKind.ai_needs, {"province_id": body.location_id})
    return {"ok": ok, "status": status}
