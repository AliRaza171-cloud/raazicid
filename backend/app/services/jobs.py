"""Rider jobs: who can take a job, proof checks, tracking. Status rules: docs/status-flow.md."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Category, Donation, FraudFlag, Job, Ngo, RiderPing, RiderProfile, User
from app.models.enums import ImageKind, JobStatus, RiderStatus, Role, Severity
from app.schemas.jobs import AdminTrackingItem, JobOut, LatLng, Place, RiderOption, ScoreReason, TrackingOut, TrackingRider
from app.services.accounts import notify
from app.services.donations import ref
from app.services.geo import distance_km
from app.services.locations import ancestor_ids, location_path
from app.services.recommend import RiderFacts, score_rider

ACTIVE_JOB = [JobStatus.assigned, JobStatus.accepted, JobStatus.picked_up]
FAR_KM = 1.0              # proof photo further than this from where it should be -> fraud flag for an admin to check
STALL_MINUTES = 10        # no GPS for this long during an active job -> "stalled" on the admin map
PK_TZ = timezone(timedelta(hours=5))


def notify_admins(db: Session, type_: str, title: str, body: str, data: dict) -> None:
    for admin in db.scalars(select(User).where(User.role == Role.admin, User.is_active.is_(True))):
        notify(db, admin, type_, title, body, data)


def raise_flag(db: Session, rule: str, severity: Severity, entity_type: str, entity_id, evidence: dict) -> None:
    db.add(FraudFlag(rule_code=rule, severity=severity, entity_type=entity_type, entity_id=entity_id, evidence=evidence))


def active_jobs(db: Session, rider_id) -> int:
    return db.scalar(select(func.count()).select_from(Job).where(Job.rider_id == rider_id, Job.status.in_(ACTIVE_JOB))) or 0


def _match(chain_pickup: list, rider_location_id, db: Session) -> str:
    names = ["same_area", "same_region", "same_city", "same_province"]
    offset = 4 - len(chain_pickup) if chain_pickup else 0
    levels = {loc: i for i, loc in enumerate(chain_pickup)}
    for loc in ancestor_ids(db, rider_location_id):
        if loc in levels:
            idx = levels[loc] + offset
            return names[idx] if idx < len(names) else "other"
    return "other"


def _facts(db: Session, d: Donation, user: User, rp: RiderProfile, chain: list) -> RiderFacts:
    fresh = datetime.now(timezone.utc) - timedelta(hours=2)
    dist = None
    if rp.last_lat is not None and rp.last_seen_at and rp.last_seen_at >= fresh:
        dist = round(distance_km(rp.last_lat, rp.last_lng, d.pickup_lat, d.pickup_lng), 1)
    return RiderFacts(distance_km=dist, area_match=_match(chain, user.location_id, db), active_jobs=active_jobs(db, user.id),
                      is_available=rp.is_available, rating_avg=rp.rating_avg, vehicle=rp.vehicle_type.value)


def rider_score(db: Session, d: Donation, user: User) -> tuple[int, list[tuple[str, int]]]:
    cat = db.get(Category, d.category_id)
    facts = _facts(db, d, user, user.rider_profile, ancestor_ids(db, d.pickup_location_id))
    return score_rider(facts, d.quantity, cat.slug if cat else "")


def rider_options(db: Session, d: Donation, limit: int = 15) -> list[RiderOption]:
    """Approved riders ranked by the recommendation score (app/services/recommend.py), best first."""
    chain = ancestor_ids(db, d.pickup_location_id)
    cat = db.get(Category, d.category_id)
    out = []
    rows = db.execute(select(User, RiderProfile).join(RiderProfile, RiderProfile.user_id == User.id)
                      .where(RiderProfile.status == RiderStatus.approved, User.is_active.is_(True))).all()
    for user, rp in rows:
        f = _facts(db, d, user, rp, chain)
        score, reasons = score_rider(f, d.quantity, cat.slug if cat else "")
        out.append(RiderOption(
            id=user.id, full_name=user.full_name, phone=user.phone, vehicle_type=rp.vehicle_type,
            vehicle_number=rp.vehicle_number, is_available=rp.is_available, active_jobs=f.active_jobs,
            match=f.area_match, distance_km=f.distance_km, last_seen_at=rp.last_seen_at, rating_avg=rp.rating_avg,
            score=score, reasons=[ScoreReason(label=l, points=p) for l, p in reasons],
        ))
    out.sort(key=lambda r: (-r.score, r.active_jobs))
    return out[:limit]


def _place_pickup(db: Session, d: Donation) -> Place:
    return Place(address=d.pickup_address, lat=d.pickup_lat, lng=d.pickup_lng,
                 area=location_path(db, d.pickup_location_id)[-2:])


def _place_ngo(db: Session, n: Optional[Ngo]) -> Optional[Place]:
    if n is None:
        return None
    return Place(name=n.name, address=n.address, lat=n.lat, lng=n.lng, area=location_path(db, n.location_id)[-2:],
                 contact_phone=n.phone, approx=n.location_approx)


def job_out(db: Session, job: Job) -> JobOut:
    d = db.get(Donation, job.donation_id)
    ngo = db.get(Ngo, d.ngo_id) if d.ngo_id else None
    donor = db.get(User, d.donor_id)
    cat = db.get(Category, d.category_id)
    shared = job.status in (JobStatus.accepted, JobStatus.picked_up)
    return JobOut(
        id=job.id, status=job.status, assigned_at=job.created_at, accepted_at=job.accepted_at,
        picked_up_at=job.picked_up_at, delivered_at=job.delivered_at, decline_reason=job.decline_reason,
        donation_id=d.id, donation_ref=ref(d), donation_status=d.status.value, title=d.title,
        category=cat.name if cat else "?", quantity=d.quantity, description=d.description, is_food=d.is_food,
        food_type=d.food_type, prepared_at=d.prepared_at, urgency_score=d.urgency_score,
        photos=[i.url for i in d.images if i.kind == ImageKind.donor_photo],
        pickup=_place_pickup(db, d), pickup_from=d.pickup_from, pickup_to=d.pickup_to, ngo=_place_ngo(db, ngo),
        donor_name=donor.full_name, donor_phone=donor.phone if shared else None,
        trip_km=round(distance_km(d.pickup_lat, d.pickup_lng, ngo.lat, ngo.lng), 1) if ngo else None,
    )


def _last_ping(db: Session, job: Job) -> Optional[RiderPing]:
    return db.scalar(select(RiderPing).where(RiderPing.job_id == job.id).order_by(RiderPing.recorded_at.desc()).limit(1))


def _stalled(job: Job, last: Optional[RiderPing], now: datetime) -> bool:
    if job.status not in (JobStatus.accepted, JobStatus.picked_up):
        return False
    since = last.recorded_at if last else (job.accepted_at or job.created_at)
    return (now - since) > timedelta(minutes=STALL_MINUTES)


def tracking(db: Session, d: Donation, job: Optional[Job]) -> TrackingOut:
    ngo = db.get(Ngo, d.ngo_id) if d.ngo_id else None
    now = datetime.now(timezone.utc)
    if job is None:
        return TrackingOut(donation_id=d.id, donation_status=d.status.value, job_id=None, job_status=None, heading_to=None,
                           rider=None, last=None, path=[], stalled=False, pickup=_place_pickup(db, d),
                           ngo=_place_ngo(db, ngo))
    rider = db.get(User, job.rider_id)
    rp = rider.rider_profile
    pings = list(db.scalars(select(RiderPing).where(RiderPing.job_id == job.id)
                            .order_by(RiderPing.recorded_at.desc()).limit(240)))[::-1]
    last = pings[-1] if pings else None
    heading = "ngo" if job.status in (JobStatus.picked_up, JobStatus.delivered) else "pickup"
    return TrackingOut(
        donation_id=d.id, donation_status=d.status.value, job_id=job.id, job_status=job.status, heading_to=heading,
        rider=TrackingRider(full_name=rider.full_name, phone=rider.phone, vehicle_type=rp.vehicle_type,
                            vehicle_number=rp.vehicle_number),
        last=LatLng(lat=last.lat, lng=last.lng, at=last.recorded_at) if last else None,
        path=[LatLng(lat=p.lat, lng=p.lng, at=p.recorded_at) for p in pings],
        stalled=_stalled(job, last, now), pickup=_place_pickup(db, d), ngo=_place_ngo(db, ngo),
    )


def admin_tracking(db: Session) -> list[AdminTrackingItem]:
    now = datetime.now(timezone.utc)
    items = []
    for job in db.scalars(select(Job).where(Job.status.in_(ACTIVE_JOB)).order_by(Job.created_at)):
        d = db.get(Donation, job.donation_id)
        rider = db.get(User, job.rider_id)
        last = _last_ping(db, job)
        ngo = db.get(Ngo, d.ngo_id) if d.ngo_id else None
        items.append(AdminTrackingItem(
            job_id=job.id, job_status=job.status, donation_id=d.id, donation_ref=ref(d), title=d.title,
            rider_name=rider.full_name, rider_phone=rider.phone,
            heading_to="ngo" if job.status == JobStatus.picked_up else "pickup",
            last=LatLng(lat=last.lat, lng=last.lng, at=last.recorded_at) if last else None,
            minutes_since_ping=int((now - last.recorded_at).total_seconds() // 60) if last else None,
            stalled=_stalled(job, last, now), pickup=_place_pickup(db, d), ngo=_place_ngo(db, ngo),
        ))
    # Stalled first, so the admin sees problems at the top
    items.sort(key=lambda i: (not i.stalled, i.minutes_since_ping is None))
    return items


def done_counts(db: Session, rider_id) -> tuple[int, int]:
    start_today = datetime.now(PK_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    base = select(func.count()).select_from(Job).where(Job.rider_id == rider_id, Job.status == JobStatus.delivered)
    return (db.scalar(base.where(Job.delivered_at >= start_today)) or 0, db.scalar(base) or 0)

