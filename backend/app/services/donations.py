"""Donation status moves and the shapes the apps read. Status rules: docs/status-flow.md."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import api_error
from app.models import Category, DistributionPoint, Donation, HandOut, Job, Location, PointRequest, StatusChange, User
from app.models.enums import DonationStatus as S
from app.models.enums import ImageKind, JobStatus, RequestStatus
from app.schemas.donations import (
    AiSuggestion, CategoryRef, DonationListItem, DonationOut, DonorRef, HandOutRef, HistoryItem, JobRef, Pickup,
    PointOption, PointRef, ProofPhoto, UrgencyReason,
)
from app.schemas.points import PointOut
from app.services.accounts import notify
from app.services.geo import distance_km
from app.services.locations import ancestor_ids, centre, coords_problem, location_path
from app.services.urgency import food_urgency

# Which moves are allowed (from -> to). Phase 4 uses the rider steps.
ALLOWED: dict[S, set[S]] = {
    S.in_review: {S.accepted, S.rejected, S.cancelled},
    S.accepted: {S.rider_assigned, S.cancelled},
    S.rider_assigned: {S.accepted, S.picked_up},
    S.picked_up: {S.at_point},
    S.at_point: {S.handed_out},
}
ACTIVE = [S.in_review, S.accepted, S.rider_assigned, S.picked_up, S.at_point]
DONE = [S.handed_out, S.rejected, S.cancelled]
CANCELLABLE = {S.in_review, S.accepted}

# What the donor is told after each move
DONOR_MESSAGES: dict[S, tuple[str, str]] = {
    S.accepted: ("Donation accepted", "We accepted \"{title}\". A rider will be assigned for pickup soon."),
    S.rejected: ("Donation not accepted", "We could not accept \"{title}\": {note}"),
    S.rider_assigned: ("Rider assigned", "A rider is coming to pick up \"{title}\"."),
    S.picked_up: ("Picked up", "\"{title}\" has been picked up. Thank you!"),
    S.at_point: ("Delivered to the point", "\"{title}\" reached {point}."),
    S.handed_out: ("Handed out", "\"{title}\" was handed out at {point}. {note} Thank you!"),
}


URGENCY_LIVE = {S.in_review, S.accepted, S.rider_assigned}   # food still waiting: urgency keeps rising


def nearest_food_point_km(db: Session, lat: float, lng: float) -> Optional[float]:
    """Distance to the nearest open point that can hand out cooked food the same day."""
    best = None
    for p in db.scalars(select(DistributionPoint).where(DistributionPoint.same_day_food.is_(True))):
        if point_is_open(p):
            km = distance_km(lat, lng, p.lat, p.lng)
            best = km if best is None or km < best else best
    return best


def urgency_for(db: Session, d: Donation, now: Optional[datetime] = None) -> tuple[Optional[int], list[tuple[str, int]]]:
    """Live score while the food is waiting; frozen at pickup time once it is on its way or done."""
    if not d.is_food:
        return None, []
    if now is None:
        now = datetime.now(timezone.utc) if d.status in URGENCY_LIVE else d.created_at
    return food_urgency(d.is_food, d.food_type, d.prepared_at, d.quantity, now,
                        nearest_food_point_km(db, d.pickup_lat, d.pickup_lng))


def refresh_urgency(db: Session) -> None:
    """Re-score waiting food donations (time since cooking keeps growing). Called before the admin list."""
    changed = False
    for d in db.scalars(select(Donation).where(Donation.is_food.is_(True), Donation.status.in_(URGENCY_LIVE))):
        score, _ = urgency_for(db, d)
        if score != d.urgency_score:
            d.urgency_score = score
            changed = True
    if changed:
        db.commit()


def ref(d: Donation) -> str:
    return "D-" + d.id.hex[:6].upper()


def change_status(
    db: Session, d: Donation, to: S, by: Optional[User], note: Optional[str] = None, tell_donor: bool = True
) -> None:
    """Move a donation, record it in the history and notify the donor. Caller commits."""
    if to not in ALLOWED.get(d.status, set()):
        raise api_error(409, "bad_status", f"A donation that is {d.status.value.replace('_', ' ')} cannot become {to.value.replace('_', ' ')}")
    db.add(StatusChange(donation_id=d.id, from_status=d.status, to_status=to, changed_by=by.id if by else None, note=note))
    d.status = to
    msg = DONOR_MESSAGES.get(to)
    if msg and tell_donor and (by is None or by.id != d.donor_id):
        donor = db.get(User, d.donor_id)
        point = db.get(DistributionPoint, d.point_id) if d.point_id else None
        title, body = msg
        notify(db, donor, f"donation_{to.value}", title,
               body.format(title=d.title, note=note or "", point=point.name if point else "the distribution point"),
               {"donation_id": str(d.id)})


def _category(db: Session, category_id: int) -> CategoryRef:
    c = db.get(Category, category_id)
    return CategoryRef(id=c.id, name=c.name) if c else CategoryRef(id=category_id, name="?")


def _first_photo(d: Donation) -> Optional[str]:
    return next((i.url for i in d.images if i.kind == ImageKind.donor_photo), None)


def list_item(db: Session, d: Donation, with_donor: bool = False) -> DonationListItem:
    point = db.get(DistributionPoint, d.point_id) if d.point_id else None
    donor = db.get(User, d.donor_id) if with_donor else None
    return DonationListItem(
        id=d.id, ref=ref(d), title=d.title, category=_category(db, d.category_id), quantity=d.quantity,
        status=d.status, is_food=d.is_food, urgency_score=d.urgency_score, photo_url=_first_photo(d),
        pickup_area=location_path(db, d.pickup_location_id)[-2:], point_name=point.name if point else None,
        donor_name=donor.full_name if donor else None, created_at=d.created_at,
    )


def donation_out(db: Session, d: Donation) -> DonationOut:
    base = list_item(db, d, with_donor=True)
    point = db.get(DistributionPoint, d.point_id) if d.point_id else None
    donor = db.get(User, d.donor_id)
    names = {u.id: u.full_name for u in db.scalars(select(User).where(User.id.in_({h.changed_by for h in d.history if h.changed_by})))}
    _, reasons = urgency_for(db, d)
    ai = (
        AiSuggestion(category_id=d.ai_category_id, confidence=d.ai_confidence or 0, top3=d.ai_top3 or [])
        if d.ai_category_id else None
    )
    return DonationOut(
        **base.model_dump(),
        description=d.description, condition=d.condition, food_type=d.food_type, prepared_at=d.prepared_at,
        urgency_reasons=[UrgencyReason(label=l, points=p) for l, p in reasons],
        pickup=Pickup(
            address=d.pickup_address, lat=d.pickup_lat, lng=d.pickup_lng, location_id=d.pickup_location_id,
            location_path=location_path(db, d.pickup_location_id), from_=d.pickup_from, to=d.pickup_to,
        ),
        point=PointRef(id=point.id, name=point.name, address=point.address, lat=point.lat, lng=point.lng,
                       location_path=location_path(db, point.location_id)) if point else None,
        reject_reason=d.reject_reason,
        photos=[i.url for i in d.images if i.kind == ImageKind.donor_photo],
        history=[
            HistoryItem(from_status=h.from_status, to_status=h.to_status, note=h.note,
                        by_name=names.get(h.changed_by) if h.changed_by else None, at=h.created_at)
            for h in d.history
        ],
        donor=DonorRef(
            id=donor.id, full_name=donor.full_name, phone=donor.phone,
            donations_count=db.scalar(select(func.count()).select_from(Donation).where(Donation.donor_id == donor.id)) or 0,
        ),
        ai=ai,
        can_cancel=d.status in CANCELLABLE,
        job=_job_ref(db, d),
        proofs=_proofs(db, d, point),
        hand_out=_hand_out(db, d),
    )


def current_job(db: Session, d: Donation) -> Optional[Job]:
    """The newest job that was not declined or cancelled."""
    return db.scalar(
        select(Job).where(Job.donation_id == d.id, Job.status.notin_([JobStatus.declined, JobStatus.cancelled]))
        .order_by(Job.created_at.desc()).limit(1)
    )


def _job_ref(db: Session, d: Donation) -> Optional[JobRef]:
    job = current_job(db, d)
    if job is None:
        return None
    rider = db.get(User, job.rider_id)
    rp = rider.rider_profile
    return JobRef(id=job.id, status=job.status.value, rider_id=rider.id, rider_name=rider.full_name, rider_phone=rider.phone,
                  vehicle=f"{rp.vehicle_type.value.title()} {rp.vehicle_number}" if rp else "", assigned_at=job.created_at)


def _proofs(db: Session, d: Donation, point: Optional[DistributionPoint]) -> list[ProofPhoto]:
    out = []
    for i in d.images:
        if i.kind == ImageKind.donor_photo:
            continue
        dist = None
        if i.lat is not None and i.lng is not None:
            if i.kind == ImageKind.pickup_proof:
                dist = round(distance_km(i.lat, i.lng, d.pickup_lat, d.pickup_lng), 2)
            elif point is not None:
                dist = round(distance_km(i.lat, i.lng, point.lat, point.lng), 2)
        out.append(ProofPhoto(kind=i.kind.value, url=i.url, lat=i.lat, lng=i.lng, distance_km=dist, at=i.created_at))
    return out


def _hand_out(db: Session, d: Donation) -> Optional[HandOutRef]:
    h = db.scalar(select(HandOut).where(HandOut.donation_id == d.id).order_by(HandOut.created_at.desc()).limit(1))
    if h is None:
        return None
    by = db.get(User, h.handed_out_by)
    return HandOutRef(quantity=h.quantity, families_served=h.families_served, photo_url=h.photo_url, note=h.note,
                      by_name=by.full_name if by else "?", at=h.created_at)


# ---------- distribution points ----------

def items_30d(db: Session, point_id: uuid.UUID) -> int:
    since = datetime.now(timezone.utc) - timedelta(days=30)
    return db.scalar(
        select(func.count()).select_from(Donation).where(
            Donation.point_id == point_id, Donation.created_at >= since,
            Donation.status.notin_([S.rejected, S.cancelled]),
        )
    ) or 0


def point_out(db: Session, p: DistributionPoint) -> PointOut:
    open_req = db.scalar(
        select(func.count()).select_from(PointRequest).where(PointRequest.point_id == p.id, PointRequest.status == RequestStatus.open)
    ) or 0
    return PointOut(
        id=p.id, name=p.name, type=p.type, location_id=p.location_id, location_path=location_path(db, p.location_id),
        address=p.address, lat=p.lat, lng=p.lng, contact_name=p.contact_name, contact_phone=p.contact_phone,
        same_day_food=p.same_day_food, is_active=p.is_active, closes_at=p.closes_at,
        categories=[CategoryRef(id=c.id, name=c.name) for c in sorted(p.categories, key=lambda c: c.id)],
        items_30d=items_30d(db, p.id), open_requests=open_req, created_at=p.created_at,
        place_warning=coords_problem(db, p.location_id, p.lat, p.lng),
        place_centre=_centre_of(db, p.location_id),
    )


def _centre_of(db: Session, location_id: uuid.UUID) -> Optional[dict]:
    c = centre(db, location_id)
    return {"name": c.name, "lat": c.lat, "lng": c.lng} if c else None


def point_is_open(p: DistributionPoint) -> bool:
    return p.is_active and (p.closes_at is None or p.closes_at > datetime.now(timezone.utc))


def point_takes(p: DistributionPoint, d: Donation) -> Optional[str]:
    """None if the point can take this donation, otherwise the reason it cannot."""
    if not point_is_open(p):
        return "This point is closed"
    if p.categories and d.category_id not in {c.id for c in p.categories}:
        return "This point does not take this category"
    if d.is_food and d.food_type is not None and d.food_type.value == "cooked" and not p.same_day_food:
        return "This point cannot hand out cooked food the same day"
    return None


def point_options(db: Session, d: Donation, limit: int = 10) -> list[PointOption]:
    """Open points that can take the donation: same area first, then region, city, province, then by distance.
    Phase 6 adds area need and what each point received recently to this ranking."""
    pickup_chain = ancestor_ids(db, d.pickup_location_id)   # [area, region, city, province]
    levels = {loc_id: i for i, loc_id in enumerate(pickup_chain)}
    names = ["same_area", "same_region", "same_city", "same_province"]
    # The pickup place may be a city or region, so match names by the place's own level
    loc_level_offset = 4 - len(pickup_chain) if pickup_chain else 0

    options = []
    for p in db.scalars(select(DistributionPoint)):
        if point_takes(p, d) is not None:
            continue
        best = "other"
        for loc_id in ancestor_ids(db, p.location_id):
            if loc_id in levels:
                idx = levels[loc_id] + loc_level_offset
                best = names[idx] if idx < len(names) else "other"
                break
        options.append(PointOption(
            id=p.id, name=p.name, type=p.type.value, location_path=location_path(db, p.location_id),
            distance_km=round(distance_km(d.pickup_lat, d.pickup_lng, p.lat, p.lng), 1),
            match=best, same_day_food=p.same_day_food, items_30d=items_30d(db, p.id),
        ))
    order = {"same_area": 0, "same_region": 1, "same_city": 2, "same_province": 3, "other": 4}
    options.sort(key=lambda o: (order[o.match], o.distance_km))
    return options[:limit]


def check_location(db: Session, location_id: uuid.UUID) -> Location:
    loc = db.get(Location, location_id)
    if loc is None:
        raise api_error(422, "bad_location", "Choose the area from the list")
    return loc
