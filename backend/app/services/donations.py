"""Donation status moves and the shapes the apps read. Status rules: docs/status-flow.md."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import api_error
from app.models import Category, Donation, Location, Ngo, StatusChange, User
from app.models.enums import DonationStatus as S
from app.models.enums import ImageKind
from app.schemas.donations import (
    CategoryRef, DonationListItem, DonationOut, DonorRef, HistoryItem, Pickup, UrgencyReason,
)
from app.services.accounts import notify
from app.services.locations import location_path
from app.services.ngos import nearest_food_ngo_km, ngo_ref
from app.services.urgency import food_urgency

# Which moves are allowed (from -> to). The rider steps (rider assigned, picked up, delivered) come in Phase 4.
ALLOWED: dict[S, set[S]] = {
    S.in_review: {S.accepted, S.rejected, S.cancelled},
    S.accepted: {S.cancelled},
}
ACTIVE = [S.in_review, S.accepted, S.rider_assigned, S.picked_up]
DONE = [S.delivered, S.rejected, S.cancelled]
CANCELLABLE = {S.in_review, S.accepted}

# What the donor is told after each move
DONOR_MESSAGES: dict[S, tuple[str, str]] = {
    S.accepted: ("Donation accepted", "We accepted \"{title}\". A rider will be assigned for pickup soon."),
    S.rejected: ("Donation not accepted", "We could not accept \"{title}\": {note}"),
}


URGENCY_LIVE = {S.in_review, S.accepted, S.rider_assigned}   # food still waiting: urgency keeps rising


def urgency_for(db: Session, d: Donation, now: Optional[datetime] = None) -> tuple[Optional[int], list[tuple[str, int]]]:
    """Live score while the food is waiting; frozen at pickup time once it is on its way or done."""
    if not d.is_food:
        return None, []
    if now is None:
        now = datetime.now(timezone.utc) if d.status in URGENCY_LIVE else d.created_at
    return food_urgency(d.is_food, d.food_type, d.prepared_at, d.quantity, now,
                        nearest_food_ngo_km(db, d.pickup_lat, d.pickup_lng))


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
        ngo = db.get(Ngo, d.ngo_id) if d.ngo_id else None
        title, body = msg
        notify(db, donor, f"donation_{to.value}", title,
               body.format(title=d.title, note=note or "", ngo=ngo.name if ngo else "the NGO"),
               {"donation_id": str(d.id)})


def _category(db: Session, category_id: int) -> CategoryRef:
    c = db.get(Category, category_id)
    return CategoryRef(id=c.id, name=c.name) if c else CategoryRef(id=category_id, name="?")


def _first_photo(d: Donation) -> Optional[str]:
    return next((i.url for i in d.images if i.kind == ImageKind.donor_photo), None)


def list_item(db: Session, d: Donation, with_donor: bool = False) -> DonationListItem:
    ngo = db.get(Ngo, d.ngo_id) if d.ngo_id else None
    donor = db.get(User, d.donor_id) if with_donor else None
    return DonationListItem(
        id=d.id, ref=ref(d), title=d.title, category=_category(db, d.category_id), quantity=d.quantity,
        status=d.status, is_food=d.is_food, urgency_score=d.urgency_score, photo_url=_first_photo(d),
        pickup_area=location_path(db, d.pickup_location_id)[-2:], ngo_name=ngo.name if ngo else None,
        donor_name=donor.full_name if donor else None, created_at=d.created_at,
    )


def donation_out(db: Session, d: Donation) -> DonationOut:
    base = list_item(db, d, with_donor=True)
    ngo = db.get(Ngo, d.ngo_id) if d.ngo_id else None
    donor = db.get(User, d.donor_id)
    names = {u.id: u.full_name for u in db.scalars(select(User).where(User.id.in_({h.changed_by for h in d.history if h.changed_by})))}
    _, reasons = urgency_for(db, d)
    return DonationOut(
        **base.model_dump(),
        description=d.description, condition=d.condition, food_type=d.food_type, prepared_at=d.prepared_at,
        urgency_reasons=[UrgencyReason(label=l, points=p) for l, p in reasons],
        pickup=Pickup(
            address=d.pickup_address, lat=d.pickup_lat, lng=d.pickup_lng, location_id=d.pickup_location_id,
            location_path=location_path(db, d.pickup_location_id), from_=d.pickup_from, to=d.pickup_to,
        ),
        ngo=ngo_ref(db, ngo),
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
        can_cancel=d.status in CANCELLABLE,
    )


def check_location(db: Session, location_id: uuid.UUID) -> Location:
    loc = db.get(Location, location_id)
    if loc is None:
        raise api_error(422, "bad_location", "Choose the area from the list")
    return loc
