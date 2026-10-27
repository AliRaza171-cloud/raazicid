"""Admin: donations table, accept (choose the NGO our rider will drop it at) or reject."""

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, nulls_last, select
from sqlalchemy.orm import Session

from app.core.deps import require_roles
from app.core.errors import api_error
from app.db.session import get_db
from app.models import Donation, Job, Ngo, User
from app.models.enums import DonationStatus, JobStatus, RiderStatus, Role
from app.schemas.donations import AcceptIn, DonationCounts, DonationList, DonationOut, NgoOption, RejectIn
from app.schemas.jobs import AdminTrackingItem, AssignIn, ReasonIn, RiderOption
from app.services.accounts import notify
from app.services.donations import change_status, current_job, donation_out, list_item, refresh_urgency
from app.services.jobs import admin_tracking, rider_options, rider_score
from app.services.locations import descendant_ids
from app.services.ngos import ngo_options, ngo_takes

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
    refresh_urgency(db)   # cooked food gets more urgent every hour it waits
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


@router.get("/{donation_id}/ngo-options", response_model=list[NgoOption])
def options(donation_id: uuid.UUID, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    """NGOs we know that take this donation, same city first. Empty? Search the web: POST /admin/ngos/search."""
    return ngo_options(db, _get(db, donation_id))


@router.post("/{donation_id}/accept", response_model=DonationOut)
def accept(donation_id: uuid.UUID, body: AcceptIn, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    d = _get(db, donation_id)
    ngo = db.get(Ngo, body.ngo_id)
    if ngo is None:
        raise api_error(404, "ngo_not_found", "NGO not found")
    reason = ngo_takes(ngo, d)
    if reason:
        raise api_error(409, "ngo_cannot_take", reason)
    d.ngo_id = ngo.id
    change_status(db, d, DonationStatus.accepted, admin, f"Going to {ngo.name}")
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


# ---------- Phase 4: riders ----------

@router.get("/{donation_id}/rider-options", response_model=list[RiderOption])
def riders_for(donation_id: uuid.UUID, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    return rider_options(db, _get(db, donation_id))


@router.post("/{donation_id}/assign", response_model=DonationOut)
def assign(donation_id: uuid.UUID, body: AssignIn, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    d = _get(db, donation_id)
    if d.status != DonationStatus.accepted:
        raise api_error(409, "bad_status", "Only accepted donations can get a rider")
    rider = db.get(User, body.rider_id)
    if rider is None or rider.rider_profile is None or rider.rider_profile.status != RiderStatus.approved or not rider.is_active:
        raise api_error(422, "rider_not_approved", "Choose an approved rider")
    score, _ = rider_score(db, d, rider)
    job = Job(donation_id=d.id, rider_id=rider.id, assigned_by=admin.id, status=JobStatus.assigned,
              recommendation_score=score)
    db.add(job)
    change_status(db, d, DonationStatus.rider_assigned, admin, f"Assigned to {rider.full_name}")
    notify(db, rider, "job_assigned", "New pickup job", f"Pick up \"{d.title}\" from {d.pickup_address}.",
           {"donation_id": str(d.id)})
    db.commit()
    db.refresh(d)
    return donation_out(db, d)


@router.post("/{donation_id}/cancel-job", response_model=DonationOut)
def cancel_job(donation_id: uuid.UUID, body: ReasonIn, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    """Take the job away from the rider before pickup (e.g. not moving). The donation goes back to 'accepted'."""
    d = _get(db, donation_id)
    job = current_job(db, d)
    if job is None or job.status not in (JobStatus.assigned, JobStatus.accepted):
        raise api_error(409, "cannot_cancel_job", "Only a job that has not been picked up yet can be cancelled")
    reason = " ".join(body.reason.split())
    job.status = JobStatus.cancelled
    job.decline_reason = reason
    change_status(db, d, DonationStatus.accepted, admin, f"Job cancelled: {reason}", tell_donor=False)
    notify(db, db.get(User, job.rider_id), "job_cancelled", "Job cancelled", f"\"{d.title}\" was taken off you: {reason}",
           {"donation_id": str(d.id)})
    db.commit()
    db.refresh(d)
    return donation_out(db, d)


tracking_router = APIRouter(prefix="/admin/tracking", tags=["admin: tracking"])


@tracking_router.get("", response_model=list[AdminTrackingItem])
def live(_: User = Depends(admin_only), db: Session = Depends(get_db)):
    """Every active job with the rider's last GPS point. The web page refreshes this every 15 s."""
    return admin_tracking(db)
