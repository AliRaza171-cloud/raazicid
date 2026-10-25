"""Appeals (Phase 6B): an admin asks donors in chosen provinces to give specific items for an area in need."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Appeal, Category, Notification, User
from app.models.enums import Role
from app.services.locations import ancestor_ids, descendant_ids, location_path


def province_of(db: Session, location_id: Optional[uuid.UUID]) -> Optional[uuid.UUID]:
    chain = ancestor_ids(db, location_id)
    return chain[-1] if chain else None


def recipients(db: Session, province_ids: list[uuid.UUID]) -> list[User]:
    """Active donors who live in one of the provinces (all donors when the list is empty)."""
    stmt = select(User).where(User.role == Role.donor, User.is_active.is_(True))
    if province_ids:
        inside: set[uuid.UUID] = set()
        for pid in province_ids:
            inside |= set(descendant_ids(db, pid))
        stmt = stmt.where(User.location_id.in_(inside))
    return list(db.scalars(stmt))


def send(db: Session, appeal: Appeal) -> int:
    """Notify donors. Returns how many were told."""
    place = " › ".join(location_path(db, appeal.location_id)[-2:])
    cats = [c.name for c in db.scalars(select(Category).where(Category.id.in_(appeal.category_ids or [])))]
    body = appeal.message if not cats else f"{appeal.message}\nNeeded: {', '.join(cats)}."
    people = recipients(db, [uuid.UUID(p) for p in appeal.target_province_ids or []])
    for u in people:
        db.add(Notification(user_id=u.id, type="appeal", title=appeal.title, body=body[:2000],
                            data={"appeal_id": str(appeal.id), "category_ids": appeal.category_ids, "place": place}))
    appeal.sent_at = datetime.now(timezone.utc)
    return len(people)


def reach(db: Session, appeal_ids: list[uuid.UUID]) -> dict[str, int]:
    """Donors notified per appeal."""
    if not appeal_ids:
        return {}
    key = Notification.data["appeal_id"].astext
    rows = db.execute(select(key, func.count()).where(Notification.type == "appeal", key.in_([str(i) for i in appeal_ids]))
                      .group_by(key)).all()
    return {k: n for k, n in rows}


def is_live(a: Appeal, now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(timezone.utc)
    return a.sent_at is not None and (a.ends_at is None or a.ends_at > now)


def for_donor(db: Session, user: User) -> list[Appeal]:
    """Live appeals for the donor's province (or sent to all of Pakistan), newest first."""
    prov = province_of(db, user.location_id)
    now = datetime.now(timezone.utc)
    rows = db.scalars(select(Appeal).where(Appeal.sent_at.isnot(None), (Appeal.ends_at.is_(None)) | (Appeal.ends_at > now))
                      .order_by(Appeal.sent_at.desc()).limit(20))
    return [a for a in rows if not a.target_province_ids or (prov and str(prov) in a.target_province_ids)]


def default_ends(days: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=days)

