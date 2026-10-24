"""Donor side: create a donation, see my donations, see one donation, cancel."""

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_roles
from app.core.errors import api_error
from app.db.session import get_db
from app.models import Category, Donation, DonationImage, StatusChange, User
from app.models.enums import DonationStatus, ImageKind, Role
from app.schemas.donations import DonationIn, DonationList, DonationOut
from app.services.donations import ACTIVE, CANCELLABLE, DONE, change_status, check_location, donation_out, list_item
from app.services.urgency import food_urgency

router = APIRouter(prefix="/donations", tags=["donations"])
donor_only = require_roles(Role.donor)


@router.post("", response_model=DonationOut, status_code=status.HTTP_201_CREATED)
def create_donation(body: DonationIn, user: User = Depends(donor_only), db: Session = Depends(get_db)):
    cat = db.get(Category, body.category_id)
    if cat is None:
        raise api_error(422, "bad_category", "Choose a category from the list")
    check_location(db, body.pickup.location_id)
    is_food = body.is_food or cat.slug == "food"
    if is_food and body.food_type is None:
        raise api_error(422, "food_type_needed", "Say whether the food is cooked or dry / packed")

    now = datetime.now(timezone.utc)
    score, _ = food_urgency(is_food, body.food_type, body.prepared_at, body.quantity, now)
    d = Donation(
        donor_id=user.id, category_id=cat.id,
        ai_category_id=body.ai.category_id if body.ai else None,
        ai_confidence=body.ai.confidence if body.ai else None,
        ai_top3=body.ai.top3 if body.ai else None,
        title=body.title, description=(body.description or "").strip() or None, quantity=body.quantity,
        condition=None if is_food else body.condition,
        is_food=is_food, food_type=body.food_type if is_food else None,
        prepared_at=body.prepared_at if is_food else None, urgency_score=score,
        pickup_address=" ".join(body.pickup.address.split()), pickup_lat=body.pickup.lat, pickup_lng=body.pickup.lng,
        pickup_location_id=body.pickup.location_id, pickup_from=body.pickup.from_, pickup_to=body.pickup.to,
        status=DonationStatus.in_review,
    )
    db.add(d)
    db.flush()
    for url in body.photo_urls:
        db.add(DonationImage(donation_id=d.id, kind=ImageKind.donor_photo, url=url, uploaded_by=user.id))
    db.add(StatusChange(donation_id=d.id, from_status=None, to_status=DonationStatus.in_review, changed_by=user.id,
                        note="Created by donor"))
    db.commit()
    db.refresh(d)
    return donation_out(db, d)


@router.get("/mine", response_model=DonationList)
def my_donations(
    filter: Literal["active", "done", "all"] = "all",
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(donor_only),
    db: Session = Depends(get_db),
):
    filters = [Donation.donor_id == user.id]
    if filter == "active":
        filters.append(Donation.status.in_(ACTIVE))
    elif filter == "done":
        filters.append(Donation.status.in_(DONE))
    total = db.scalar(select(func.count()).select_from(Donation).where(*filters)) or 0
    rows = db.scalars(select(Donation).where(*filters).order_by(Donation.created_at.desc()).limit(limit).offset(offset))
    return DonationList(items=[list_item(db, d) for d in rows], total=total)


def _get_visible(db: Session, donation_id: uuid.UUID, user: User) -> Donation:
    d = db.get(Donation, donation_id)
    # Phase 4: the rider on the job can see it too
    if d is None or (user.role != Role.admin and d.donor_id != user.id):
        raise api_error(404, "donation_not_found", "Donation not found")
    return d


@router.get("/{donation_id}", response_model=DonationOut)
def get_donation(donation_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return donation_out(db, _get_visible(db, donation_id, user))


@router.post("/{donation_id}/cancel", response_model=DonationOut)
def cancel_donation(donation_id: uuid.UUID, user: User = Depends(donor_only), db: Session = Depends(get_db)):
    d = _get_visible(db, donation_id, user)
    if d.status not in CANCELLABLE:
        raise api_error(409, "cannot_cancel", "This donation can no longer be cancelled. Contact RAAZICID if needed")
    change_status(db, d, DonationStatus.cancelled, user, "Cancelled by donor")
    db.commit()
    db.refresh(d)
    return donation_out(db, d)
