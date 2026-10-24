"""Distribution points: list and detail (admin, approved riders), create and edit (admin), point requests."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_roles
from app.core.errors import api_error
from app.db.session import get_db
from app.models import Category, DistributionPoint, PointRequest, User
from app.models.enums import RequestStatus, RiderStatus, Role
from app.schemas.donations import CategoryRef
from app.schemas.points import PointDetail, PointIn, PointOut, PointRequestIn, PointRequestOut, PointRequestUpdate, PointUpdate
from app.services.donations import check_location, point_is_open, point_out
from app.services.locations import descendant_ids

router = APIRouter(tags=["distribution points"])
admin_only = require_roles(Role.admin)


def staff(user: User = Depends(get_current_user)) -> User:
    """Admins, and riders an admin has approved."""
    if user.role == Role.admin:
        return user
    if user.role == Role.rider and user.rider_profile and user.rider_profile.status == RiderStatus.approved:
        return user
    raise api_error(403, "forbidden", "You do not have access to this")


def _categories(db: Session, ids: list[int]) -> list[Category]:
    cats = list(db.scalars(select(Category).where(Category.id.in_(set(ids))))) if ids else []
    if len(cats) != len(set(ids)):
        raise api_error(422, "bad_category", "One of the categories does not exist")
    return cats


def _get(db: Session, point_id: uuid.UUID) -> DistributionPoint:
    p = db.get(DistributionPoint, point_id)
    if p is None:
        raise api_error(404, "point_not_found", "Distribution point not found")
    return p


def _requests(db: Session, p: DistributionPoint) -> list[PointRequestOut]:
    rows = db.scalars(select(PointRequest).where(PointRequest.point_id == p.id).order_by(PointRequest.created_at.desc()).limit(50))
    out = []
    for r in rows:
        cat = db.get(Category, r.category_id)
        by = db.get(User, r.requested_by)
        out.append(PointRequestOut(id=r.id, category=CategoryRef(id=cat.id, name=cat.name), quantity=r.quantity,
                                   note=r.note, status=r.status, requested_by_name=by.full_name if by else "?",
                                   created_at=r.created_at))
    return out


@router.get("/points", response_model=list[PointOut])
def list_points(
    location_id: Optional[uuid.UUID] = Query(None, description="Province, city, region or area"),
    category_id: Optional[int] = None,
    open_only: bool = False,
    user: User = Depends(staff),
    db: Session = Depends(get_db),
):
    stmt = select(DistributionPoint).order_by(DistributionPoint.name)
    if location_id:
        stmt = stmt.where(DistributionPoint.location_id.in_(descendant_ids(db, location_id)))
    points = list(db.scalars(stmt))
    if category_id:
        points = [p for p in points if not p.categories or category_id in {c.id for c in p.categories}]
    if open_only or user.role == Role.rider:
        points = [p for p in points if point_is_open(p)]
    return [point_out(db, p) for p in points]


@router.get("/points/{point_id}", response_model=PointDetail)
def get_point(point_id: uuid.UUID, _: User = Depends(staff), db: Session = Depends(get_db)):
    p = _get(db, point_id)
    return PointDetail(**point_out(db, p).model_dump(), requests=_requests(db, p))


@router.post("/admin/points", response_model=PointDetail, status_code=status.HTTP_201_CREATED)
def create_point(body: PointIn, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    check_location(db, body.location_id)
    data = body.model_dump(exclude={"category_ids"})
    p = DistributionPoint(**data)
    p.categories = _categories(db, body.category_ids)
    db.add(p)
    db.commit()
    db.refresh(p)
    return PointDetail(**point_out(db, p).model_dump(), requests=[])


@router.patch("/admin/points/{point_id}", response_model=PointDetail)
def update_point(point_id: uuid.UUID, body: PointUpdate, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    p = _get(db, point_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("location_id"):
        check_location(db, data["location_id"])
    if "category_ids" in data:
        p.categories = _categories(db, data.pop("category_ids") or [])
    for required in ("name", "type", "location_id", "address", "lat", "lng", "same_day_food", "is_active"):
        if required in data and data[required] is None:
            data.pop(required)   # these cannot be cleared
    for key, value in data.items():
        setattr(p, key, value)
    db.commit()
    db.refresh(p)
    return PointDetail(**point_out(db, p).model_dump(), requests=_requests(db, p))


@router.post("/points/{point_id}/requests", response_model=PointRequestOut, status_code=status.HTTP_201_CREATED)
def add_request(point_id: uuid.UUID, body: PointRequestIn, user: User = Depends(staff), db: Session = Depends(get_db)):
    """What people at the point are asking for. Feeds 'needs by area' in Phase 6."""
    p = _get(db, point_id)
    cat = db.get(Category, body.category_id)
    if cat is None:
        raise api_error(422, "bad_category", "Choose a category from the list")
    r = PointRequest(point_id=p.id, category_id=cat.id, quantity=body.quantity,
                     note=(body.note or "").strip() or None, requested_by=user.id)
    db.add(r)
    db.commit()
    db.refresh(r)
    return PointRequestOut(id=r.id, category=CategoryRef(id=cat.id, name=cat.name), quantity=r.quantity, note=r.note,
                           status=r.status, requested_by_name=user.full_name, created_at=r.created_at)


@router.patch("/admin/point-requests/{request_id}", response_model=PointRequestOut)
def update_request(request_id: uuid.UUID, body: PointRequestUpdate, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    r = db.get(PointRequest, request_id)
    if r is None:
        raise api_error(404, "request_not_found", "Request not found")
    r.status = body.status
    db.commit()
    db.refresh(r)
    cat = db.get(Category, r.category_id)
    by = db.get(User, r.requested_by)
    return PointRequestOut(id=r.id, category=CategoryRef(id=cat.id, name=cat.name), quantity=r.quantity, note=r.note,
                           status=r.status, requested_by_name=by.full_name if by else "?", created_at=r.created_at)
