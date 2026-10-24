"""Admin: donations table, accept (choose a distribution point) or reject."""

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, nulls_last, select
from sqlalchemy.orm import Session

from app.core.deps import require_roles
from app.core.errors import api_error
from app.db.session import get_db
from app.models import DistributionPoint, Donation, User
from app.models.enums import DonationStatus, Role
from app.schemas.donations import AcceptIn, DonationCounts, DonationList, DonationOut, PointOption, RejectIn
from app.services.donations import change_status, donation_out, list_item, point_options, point_takes
from app.services.locations import descendant_ids

router = APIRouter(prefix="/admin/donations", tags=["admin: donations"])
admin_only = require_roles(Role.admin)


@router.get("/counts", response_model=DonationCounts)
def counts(_: User = Depends(admin_only), db: Session = Depends(get_db)):
    rows = dict(db.execute(select(Donation.status, func.count()).group_by(Donation.status)).all())
    return DonationCounts(**{s.value: rows.get(s, 0) for s in DonationStatus})


@router.get("", response_model=DonationList)
def list_donations(
    status: Optional[DonationStatus] = None,
    category_id: Optional[int] = None,
    location_id: Optional[uuid.UUID] = Query(None, description="Province, city, region or area: includes everything under it"),
    q: Optional[str] = Query(None, description="Search title, donor name or phone"),
    sort: Literal["urgency", "newest", "oldest"] = "urgency",
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: User = Depends(admin_only),
    db: Session = Depends(get_db),
):
    filters = []
    if status:
        filters.append(Donation.status == status)
    if category_id:
        filters.append(Donation.category_id == category_id)
    if location_id:
        filters.append(Donation.pickup_location_id.in_(descendant_ids(db, location_id)))
    if q and q.strip():
        like = f"%{q.strip()}%"
        donor_ids = select(User.id).where(User.full_name.ilike(like) | User.phone.ilike(like))
        filters.append(Donation.title.ilike(like) | Donation.donor_id.in_(donor_ids))

    order = {
        "urgency": [nulls_last(Donation.urgency_score.desc()), Donation.created_at.asc()],
        "newest": [Donation.created_at.desc()],
        "oldest": [Donation.created_at.asc()],
    }[sort]
    total = db.scalar(select(func.count()).select_from(Donation).where(*filters)) or 0
    rows = db.scalars(select(Donation).where(*filters).order_by(*order).limit(limit).offset(offset))
    return DonationList(items=[list_item(db, d, with_donor=True) for d in rows], total=total)


def _get(db: Session, donation_id: uuid.UUID) -> Donation:
    d = db.get(Donation, donation_id)
    if d is None:
        raise api_error(404, "donation_not_found", "Donation not found")
    return d


@router.get("/{donation_id}/point-options", response_model=list[PointOption])
def options(donation_id: uuid.UUID, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    return point_options(db, _get(db, donation_id))


@router.post("/{donation_id}/accept", response_model=DonationOut)
def accept(donation_id: uuid.UUID, body: AcceptIn, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    d = _get(db, donation_id)
    point = db.get(DistributionPoint, body.point_id)
    if point is None:
        raise api_error(404, "point_not_found", "Distribution point not found")
    reason = point_takes(point, d)
    if reason:
        raise api_error(409, "point_cannot_take", reason)
    d.point_id = point.id   # set before the move so the donor's message names the point
    change_status(db, d, DonationStatus.accepted, admin, f"Going to {point.name}")
    db.commit()
    db.refresh(d)
    return donation_out(db, d)


@router.post("/{donation_id}/reject", response_model=DonationOut)
def reject(donation_id: uuid.UUID, body: RejectIn, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    d = _get(db, donation_id)
    reason = " ".join(body.reason.split())
    change_status(db, d, DonationStatus.rejected, admin, reason)
    d.reject_reason = reason
    db.commit()
    db.refresh(d)
    return donation_out(db, d)
