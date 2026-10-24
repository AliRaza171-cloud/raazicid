"""Admin: review riders, look at their documents, approve / reject / suspend / ask for a document."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import require_roles
from app.core.errors import api_error
from app.db.session import get_db
from app.models import RiderDocument, RiderProfile, User
from app.models.enums import RiderStatus, Role
from app.schemas.auth import RiderDocOut
from app.schemas.riders import DecisionIn, RiderCounts, RiderDetail, RiderList, RiderListItem
from app.services.accounts import notify
from app.services.locations import location_path

router = APIRouter(prefix="/admin/riders", tags=["admin: riders"])
admin_only = require_roles(Role.admin)


def _doc_count(db: Session, rider_id: uuid.UUID) -> int:
    return db.scalar(select(func.count()).select_from(RiderDocument).where(RiderDocument.rider_id == rider_id)) or 0


def _item(db: Session, user: User, rp: RiderProfile) -> RiderListItem:
    return RiderListItem(
        id=user.id, full_name=user.full_name, phone=user.phone,
        vehicle_type=rp.vehicle_type, vehicle_number=rp.vehicle_number, status=rp.status,
        location_path=location_path(db, user.location_id), documents_count=_doc_count(db, user.id),
        created_at=user.created_at,
    )


@router.get("/counts", response_model=RiderCounts)
def counts(_: User = Depends(admin_only), db: Session = Depends(get_db)):
    rows = dict(db.execute(select(RiderProfile.status, func.count()).group_by(RiderProfile.status)).all())
    return RiderCounts(**{s.value: rows.get(s, 0) for s in RiderStatus})


@router.get("", response_model=RiderList)
def list_riders(
    status: Optional[RiderStatus] = None,
    q: Optional[str] = Query(None, description="Search name or phone"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: User = Depends(admin_only),
    db: Session = Depends(get_db),
):
    filters = []
    if status:
        filters.append(RiderProfile.status == status)
    if q:
        like = f"%{q.strip()}%"
        filters.append((User.full_name.ilike(like)) | (User.phone.ilike(like)))
    joined = lambda s: s.join(RiderProfile, RiderProfile.user_id == User.id).where(*filters)  # noqa: E731
    total = db.scalar(joined(select(func.count(User.id)).select_from(User))) or 0
    rows = db.execute(joined(select(User, RiderProfile)).order_by(User.created_at.desc()).limit(limit).offset(offset)).all()
    return RiderList(items=[_item(db, u, rp) for u, rp in rows], total=total)


@router.get("/{rider_id}", response_model=RiderDetail)
def rider_detail(rider_id: uuid.UUID, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    user = db.get(User, rider_id)
    if user is None or user.rider_profile is None:
        raise api_error(404, "rider_not_found", "Rider not found")
    rp = user.rider_profile
    docs = db.scalars(select(RiderDocument).where(RiderDocument.rider_id == user.id).order_by(RiderDocument.created_at))
    base = _item(db, user, rp)
    return RiderDetail(
        **base.model_dump(),
        email=user.email,
        review_note=rp.review_note,
        reviewed_at=rp.reviewed_at,
        documents=[RiderDocOut(id=d.id, doc_type=d.doc_type, file_url=d.file_url, created_at=d.created_at) for d in docs],
    )


@router.post("/{rider_id}/decision", response_model=RiderDetail)
def decide(rider_id: uuid.UUID, body: DecisionIn, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    user = db.get(User, rider_id)
    if user is None or user.rider_profile is None:
        raise api_error(404, "rider_not_found", "Rider not found")
    rp = user.rider_profile
    note = (body.note or "").strip() or None

    if body.action == "approve":
        if _doc_count(db, user.id) == 0:
            raise api_error(409, "no_documents", "This rider has not uploaded any documents yet")
        rp.status = RiderStatus.approved
        notify(db, user, "rider_approved", "You are approved", "You can now go online and take jobs.")
    elif body.action == "reject":
        rp.status = RiderStatus.rejected
        rp.is_available = False
        notify(db, user, "rider_rejected", "Application not approved", note or "")
    elif body.action == "suspend":
        rp.status = RiderStatus.suspended
        rp.is_available = False
        notify(db, user, "rider_suspended", "Account suspended", note or "")
    else:  # request_document
        rp.status = RiderStatus.pending
        notify(db, user, "rider_document_requested", "Please upload a document again", note or "")

    rp.review_note = note
    rp.reviewed_by = admin.id
    rp.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    return rider_detail(rider_id, admin, db)
