"""Appeals to donors and in-app notifications (Phase 6B)."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_roles
from app.core.errors import api_error
from app.db.session import get_db
from app.models import Appeal, Category, DisasterAlert, Location, Notification, User
from app.models.enums import LocationLevel, Role
from app.services import appeals as svc
from app.services.locations import location_path

router = APIRouter(tags=["appeals"])
admin_only = require_roles(Role.admin)


class AppealIn(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    message: str = Field(min_length=10, max_length=1500)
    location_id: uuid.UUID                       # the area the appeal is for
    category_ids: list[int] = Field(default_factory=list, max_length=12)
    province_ids: list[uuid.UUID] = Field(default_factory=list)   # who receives it; empty = the area's province
    all_pakistan: bool = False
    alert_id: Optional[uuid.UUID] = None
    days: int = Field(default=14, ge=1, le=90)


class AppealOut(BaseModel):
    id: uuid.UUID
    title: str
    message: str
    place: list[str]
    location_id: uuid.UUID
    categories: list[dict]
    provinces: list[str]
    alert_id: Optional[uuid.UUID]
    sent_at: Optional[datetime]
    ends_at: Optional[datetime]
    live: bool
    reached: int


class NotificationOut(BaseModel):
    id: uuid.UUID
    type: str
    title: str
    body: str
    data: dict
    created_at: datetime
    read: bool


def appeal_out(db: Session, a: Appeal, reached: int = 0) -> AppealOut:
    cats = {c.id: c.name for c in db.scalars(select(Category))}
    provs = [db.get(Location, uuid.UUID(p)) for p in a.target_province_ids or []]
    return AppealOut(id=a.id, title=a.title, message=a.message, place=location_path(db, a.location_id), location_id=a.location_id,
                     categories=[{"id": i, "name": cats.get(i, "?")} for i in a.category_ids or []],
                     provinces=[p.name for p in provs if p] or ["All Pakistan"], alert_id=a.alert_id, sent_at=a.sent_at,
                     ends_at=a.ends_at, live=svc.is_live(a), reached=reached)


# ---------- admin ----------

@router.post("/admin/appeals", response_model=AppealOut, status_code=201)
def create(body: AppealIn, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    if db.get(Location, body.location_id) is None:
        raise api_error(422, "bad_location", "Choose the area from the list")
    valid = {c.id for c in db.scalars(select(Category))}
    if any(c not in valid for c in body.category_ids):
        raise api_error(422, "bad_category", "Unknown category")
    if body.alert_id and db.get(DisasterAlert, body.alert_id) is None:
        raise api_error(422, "bad_alert", "Alert not found")
    if body.all_pakistan:
        provinces: list[str] = []
    else:
        ids = body.province_ids or [svc.province_of(db, body.location_id)]
        for pid in ids:
            loc = db.get(Location, pid) if pid else None
            if loc is None or loc.level != LocationLevel.province:
                raise api_error(422, "bad_province", "Choose provinces to send the appeal to")
        provinces = [str(p) for p in dict.fromkeys(ids)]
    a = Appeal(title=" ".join(body.title.split()), message=body.message.strip(), location_id=body.location_id,
               category_ids=list(dict.fromkeys(body.category_ids)), target_province_ids=provinces, created_by=admin.id,
               alert_id=body.alert_id, ends_at=svc.default_ends(body.days))
    db.add(a)
    db.flush()
    n = svc.send(db, a)
    db.commit()
    return appeal_out(db, a, n)


@router.get("/admin/appeals", response_model=list[AppealOut])
def all_appeals(alert_id: Optional[uuid.UUID] = None, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    stmt = select(Appeal).order_by(Appeal.created_at.desc()).limit(100)
    if alert_id:
        stmt = stmt.where(Appeal.alert_id == alert_id)
    rows = list(db.scalars(stmt))
    reach = svc.reach(db, [a.id for a in rows])
    return [appeal_out(db, a, reach.get(str(a.id), 0)) for a in rows]


@router.post("/admin/appeals/{appeal_id}/end", response_model=AppealOut)
def end(appeal_id: uuid.UUID, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    a = db.get(Appeal, appeal_id)
    if a is None:
        raise api_error(404, "appeal_not_found", "Appeal not found")
    a.ends_at = datetime.now(timezone.utc)
    db.commit()
    return appeal_out(db, a, svc.reach(db, [a.id]).get(str(a.id), 0))


# ---------- donors ----------

@router.get("/appeals/active", response_model=list[AppealOut])
def active(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Live appeals for my province or for all of Pakistan."""
    return [appeal_out(db, a) for a in svc.for_donor(db, user)]


@router.get("/me/notifications")
def my_notifications(limit: int = Query(40, ge=1, le=100), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(limit))
    unread = db.scalar(select(func.count()).select_from(Notification)
                       .where(Notification.user_id == user.id, Notification.read_at.is_(None))) or 0
    items = [NotificationOut(id=n.id, type=n.type, title=n.title, body=n.body, data=n.data or {}, created_at=n.created_at,
                             read=n.read_at is not None) for n in rows]
    return {"unread": unread, "items": items}


@router.post("/me/notifications/read")
def mark_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.execute(update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
               .values(read_at=datetime.now(timezone.utc)))
    db.commit()
    return {"unread": 0}
