"""Rider app: availability, my jobs, accept / decline, pickup and delivery proof, live GPS."""

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.errors import api_error
from app.db.session import get_db
from app.models import Donation, DonationImage, Job, Ngo, RiderPing, User
from app.models.enums import DonationStatus, ImageKind, JobStatus, RiderStatus, Role, Severity
from app.schemas.jobs import AvailabilityIn, JobList, JobOut, PingIn, ProofIn, ReasonIn, RiderSummary
from app.services.donations import change_status
from app.services.geo import distance_km
from app.services.jobs import ACTIVE_JOB, FAR_KM, active_jobs, done_counts, job_out, notify_admins, raise_flag

router = APIRouter(prefix="/rider", tags=["rider"])


def approved_rider(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.rider:
        raise api_error(403, "forbidden", "Only riders can do this")
    if user.rider_profile is None or user.rider_profile.status != RiderStatus.approved:
        raise api_error(403, "rider_not_approved", "Your rider account is not approved yet")
    return user


def _my_job(db: Session, job_id: uuid.UUID, rider: User) -> Job:
    job = db.get(Job, job_id)
    if job is None or job.rider_id != rider.id:
        raise api_error(404, "job_not_found", "Job not found")
    return job


def _need(job: Job, *allowed: JobStatus) -> None:
    if job.status not in allowed:
        raise api_error(409, "bad_job_status", f"This job is {job.status.value.replace('_', ' ')}")


@router.get("/summary", response_model=RiderSummary)
def summary(rider: User = Depends(approved_rider), db: Session = Depends(get_db)):
    today, total = done_counts(db, rider.id)
    rp = rider.rider_profile
    return RiderSummary(is_available=rp.is_available, active_jobs=active_jobs(db, rider.id), done_today=today,
                        done_total=total, rating_avg=rp.rating_avg)


@router.patch("/availability", response_model=RiderSummary)
def set_availability(body: AvailabilityIn, rider: User = Depends(approved_rider), db: Session = Depends(get_db)):
    rider.rider_profile.is_available = body.is_available
    db.commit()
    return summary(rider, db)


@router.get("/jobs", response_model=JobList)
def my_jobs(
    filter: Literal["current", "history"] = "current",
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    rider: User = Depends(approved_rider),
    db: Session = Depends(get_db),
):
    if filter == "current":
        cond = Job.status.in_(ACTIVE_JOB)
        order = Job.created_at.asc()
    else:
        cond = Job.status.notin_(ACTIVE_JOB)
        order = Job.created_at.desc()
    where = [Job.rider_id == rider.id, cond]
    total = db.scalar(select(func.count()).select_from(Job).where(*where)) or 0
    jobs = db.scalars(select(Job).where(*where).order_by(order).limit(limit).offset(offset))
    return JobList(items=[job_out(db, j) for j in jobs], total=total)


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID, rider: User = Depends(approved_rider), db: Session = Depends(get_db)):
    return job_out(db, _my_job(db, job_id, rider))


@router.post("/jobs/{job_id}/accept", response_model=JobOut)
def accept_job(job_id: uuid.UUID, rider: User = Depends(approved_rider), db: Session = Depends(get_db)):
    job = _my_job(db, job_id, rider)
    _need(job, JobStatus.assigned)
    job.status = JobStatus.accepted
    job.accepted_at = datetime.now(timezone.utc)
    db.commit()
    return job_out(db, job)


@router.post("/jobs/{job_id}/decline", response_model=JobOut)
def decline_job(job_id: uuid.UUID, body: ReasonIn, rider: User = Depends(approved_rider), db: Session = Depends(get_db)):
    """Give the job back before pickup. The donation goes back to 'accepted' for the admin to reassign."""
    job = _my_job(db, job_id, rider)
    _need(job, JobStatus.assigned, JobStatus.accepted)
    reason = " ".join(body.reason.split())
    job.status = JobStatus.declined
    job.decline_reason = reason
    d = db.get(Donation, job.donation_id)
    change_status(db, d, DonationStatus.accepted, rider, f"Rider declined: {reason}", tell_donor=False)
    notify_admins(db, "job_declined", "Rider declined a job", f"{rider.full_name} declined \"{d.title}\": {reason}",
                  {"donation_id": str(d.id), "job_id": str(job.id)})
    db.commit()
    return job_out(db, job)


def _save_proof(db: Session, job: Job, rider: User, d: Donation, kind: ImageKind, body: ProofIn) -> None:
    db.add(DonationImage(donation_id=d.id, kind=kind, url=body.photo_url, uploaded_by=rider.id, lat=body.lat, lng=body.lng))
    _record_ping(db, job, rider, body.lat, body.lng)


@router.post("/jobs/{job_id}/pickup", response_model=JobOut)
def picked_up(job_id: uuid.UUID, body: ProofIn, rider: User = Depends(approved_rider), db: Session = Depends(get_db)):
    """Photo of the items at the donor's place, with GPS. Far from the pickup address -> flag for an admin."""
    job = _my_job(db, job_id, rider)
    _need(job, JobStatus.accepted)
    d = db.get(Donation, job.donation_id)
    _save_proof(db, job, rider, d, ImageKind.pickup_proof, body)
    far = distance_km(body.lat, body.lng, d.pickup_lat, d.pickup_lng)
    if far > FAR_KM:
        raise_flag(db, "far_from_pickup", Severity.medium, "job", job.id,
                   {"distance_km": round(far, 2), "donation_id": str(d.id), "rider_id": str(rider.id)})
    job.status = JobStatus.picked_up
    job.picked_up_at = datetime.now(timezone.utc)
    change_status(db, d, DonationStatus.picked_up, rider, body.note)
    db.commit()
    return job_out(db, job)


@router.post("/jobs/{job_id}/deliver", response_model=JobOut)
def delivered(job_id: uuid.UUID, body: ProofIn, rider: User = Depends(approved_rider), db: Session = Depends(get_db)):
    """Photo of the items handed to the NGO, with GPS: the last step. Far from the NGO -> flag for an admin.
    When we only knew the NGO's city, the delivery GPS becomes its location for next time."""
    job = _my_job(db, job_id, rider)
    _need(job, JobStatus.picked_up)
    d = db.get(Donation, job.donation_id)
    ngo = db.get(Ngo, d.ngo_id) if d.ngo_id else None
    _save_proof(db, job, rider, d, ImageKind.delivery_proof, body)
    if ngo is None:
        pass   # a donation already on its way when distribution points were replaced by NGOs
    elif ngo.location_approx:
        ngo.lat, ngo.lng, ngo.location_approx = body.lat, body.lng, False
    else:
        far = distance_km(body.lat, body.lng, ngo.lat, ngo.lng)
        if far > FAR_KM:
            raise_flag(db, "far_from_ngo", Severity.high, "job", job.id,
                       {"distance_km": round(far, 2), "donation_id": str(d.id), "ngo_id": str(ngo.id), "rider_id": str(rider.id)})
    job.status = JobStatus.delivered
    job.delivered_at = datetime.now(timezone.utc)
    change_status(db, d, DonationStatus.delivered, rider, body.note or f"Delivered to {ngo.name if ngo else 'the NGO'}")
    db.commit()
    return job_out(db, job)


def _record_ping(db: Session, job: Job, rider: User, lat: float, lng: float) -> None:
    now = datetime.now(timezone.utc)
    db.add(RiderPing(job_id=job.id, lat=lat, lng=lng, recorded_at=now))
    rp = rider.rider_profile
    rp.last_lat, rp.last_lng, rp.last_seen_at = lat, lng, now


@router.post("/jobs/{job_id}/ping", status_code=status.HTTP_204_NO_CONTENT)
def ping(job_id: uuid.UUID, body: PingIn, rider: User = Depends(approved_rider), db: Session = Depends(get_db)):
    """Sent by the app about every 15 s while the job screen is open."""
    job = _my_job(db, job_id, rider)
    _need(job, JobStatus.accepted, JobStatus.picked_up)
    _record_ping(db, job, rider, body.lat, body.lng)
    db.commit()
