"""Disaster alerts (Phase 6): list, confirm / dismiss, what is needed, NGOs nearby; data sources status."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services import llm
from app.core.deps import get_current_user, require_roles
from app.core.errors import api_error
from app.db.session import get_db
from app.models import AlertNeed, Category, DisasterAlert, Location, Ngo, Source, User
from app.models.enums import AlertSeverity, AlertStatus, AlertType, Role, SourceKind
from app.services.locations import descendant_ids, location_path
from app.services.needs import families, recompute, suggest_alert_needs
from app.services.ngos import search_place
from app.services.relief import recommend
from app.services.sources.runner import run_source

router = APIRouter(tags=["alerts"])
admin_only = require_roles(Role.admin)
ACTIVE_DAYS = 30


# ---------- shapes ----------

class AlertPlace(BaseModel):
    id: uuid.UUID
    name: str
    path: list[str]
    lat: Optional[float]
    lng: Optional[float]


class AlertNeedOut(BaseModel):
    category_id: int
    name: str
    quantity_needed: Optional[int]
    quantity_pledged: int


class Recommendation(BaseModel):
    category_id: int
    name: str
    when: Literal["now", "soon", "later"]
    why: str
    per_family: float
    quantity: Optional[int]
    listed: bool   # already in "what is needed"


class AlertSource(BaseModel):
    title: str
    url: Optional[str]
    publisher: Optional[str]
    published_at: Optional[datetime]


class AlertOut(BaseModel):
    id: uuid.UUID
    type: AlertType
    severity: AlertSeverity
    status: AlertStatus
    title: str
    summary: Optional[str]
    figures: dict
    started_at: Optional[datetime]
    created_at: datetime
    confirmed_at: Optional[datetime]
    from_gdacs: bool
    places: list[AlertPlace]
    needs: list[AlertNeedOut]
    recommended: list[Recommendation] = []   # what to donate for this disaster, by priority, with a reason
    recommend_notes: list[str] = []          # season, time since the start, watch alerts
    families: Optional[int] = None           # affected families used for the quantities
    sources: list[AlertSource]
    ngos: list[dict] = []                    # NGOs we know in the alert's cities: where riders can take donations


class AlertIn(BaseModel):
    type: AlertType
    severity: AlertSeverity
    title: str = Field(min_length=3, max_length=200)
    summary: Optional[str] = Field(default=None, max_length=2000)
    location_ids: list[uuid.UUID] = Field(min_length=1)
    figures: dict[str, int] = Field(default_factory=dict)


class StatusIn(BaseModel):
    status: Literal["confirmed", "dismissed", "handled", "unconfirmed"]


class NeedIn(BaseModel):
    category_id: int
    quantity_needed: Optional[int] = Field(default=None, ge=0, le=10_000_000)




# ---------- helpers ----------

def alert_out(db: Session, a: DisasterAlert) -> AlertOut:
    all_cats = list(db.scalars(select(Category)))
    cats = {c.id: c.name for c in all_cats}
    by_slug = {c.slug: c for c in all_cats}
    fam = families(a.reported_figures or {})
    started = (a.started_at or a.created_at or datetime.now(timezone.utc)).date()
    advice, notes = recommend(a.type, a.severity, datetime.now(timezone.utc).date(), started, fam)
    listed = {n.category_id for n in a.needs}
    recommended = [Recommendation(category_id=by_slug[x.slug].id, name=by_slug[x.slug].name, when=x.when, why=x.why,
                                  per_family=x.per_family, quantity=x.quantity, listed=by_slug[x.slug].id in listed)
                   for x in advice if x.slug in by_slug]
    return AlertOut(
        recommended=recommended, recommend_notes=notes, families=fam,
        id=a.id, type=a.type, severity=a.severity, status=a.status, title=a.title, summary=a.summary,
        figures=a.reported_figures or {}, started_at=a.started_at, created_at=a.created_at, confirmed_at=a.confirmed_at,
        from_gdacs=bool(a.gdacs_event_id),
        places=[AlertPlace(id=l.id, name=l.name, path=location_path(db, l.id), lat=l.lat, lng=l.lng) for l in a.locations],
        needs=[AlertNeedOut(category_id=n.category_id, name=cats.get(n.category_id, "?"), quantity_needed=n.quantity_needed,
                            quantity_pledged=n.quantity_pledged) for n in sorted(a.needs, key=lambda n: n.category_id)],
        sources=[AlertSource(title=r.title, url=r.url, publisher=r.publisher, published_at=r.published_at) for r in a.reports],
        ngos=_ngos_near(db, a),
    )


def _ngos_near(db: Session, a: DisasterAlert) -> list[dict]:
    """NGOs in the cities of the alert's places (the alert may name a district or an area)."""
    out, seen = [], set()
    for loc in a.locations:
        city = search_place(db, loc.id)
        if city is None or city.id in seen:
            continue
        seen.add(city.id)
        inside = descendant_ids(db, city.id)
        for n in db.scalars(select(Ngo).where(Ngo.location_id.in_(inside), Ngo.is_active.is_(True)).order_by(Ngo.name)):
            out.append({"id": str(n.id), "name": n.name, "city": city.name, "city_id": str(city.id), "phone": n.phone,
                        "address": n.address})
    return out


def _get(db: Session, alert_id: uuid.UUID) -> DisasterAlert:
    a = db.get(DisasterAlert, alert_id)
    if a is None:
        raise api_error(404, "alert_not_found", "Alert not found")
    return a


# ---------- everyone logged in ----------

@router.get("/alerts", response_model=list[AlertOut])
def active_alerts(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Confirmed disasters of the last 30 days, newest first (donor app)."""
    since = datetime.now(timezone.utc) - timedelta(days=ACTIVE_DAYS)
    rows = db.scalars(select(DisasterAlert).where(DisasterAlert.status == AlertStatus.confirmed, DisasterAlert.created_at >= since)
                      .order_by(DisasterAlert.created_at.desc()))
    return [alert_out(db, a) for a in rows]


# ---------- admin ----------

@router.get("/admin/alerts", response_model=list[AlertOut])
def all_alerts(status: Optional[AlertStatus] = None, limit: int = Query(50, ge=1, le=200),
               _: User = Depends(admin_only), db: Session = Depends(get_db)):
    stmt = select(DisasterAlert).order_by(DisasterAlert.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(DisasterAlert.status == status)
    return [alert_out(db, a) for a in db.scalars(stmt)]


@router.get("/admin/alerts/counts")
def counts(_: User = Depends(admin_only), db: Session = Depends(get_db)):
    rows = dict(db.execute(select(DisasterAlert.status, func.count()).group_by(DisasterAlert.status)).all())
    return {s.value: rows.get(s, 0) for s in AlertStatus}


@router.get("/admin/alerts/{alert_id}", response_model=AlertOut)
def one(alert_id: uuid.UUID, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    return alert_out(db, _get(db, alert_id))


@router.post("/admin/alerts", response_model=AlertOut, status_code=201)
def create(body: AlertIn, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    """An alert the admin heard about directly (phone call, field team). Confirmed straight away."""
    locs = [db.get(Location, i) for i in body.location_ids]
    if any(l is None for l in locs):
        raise api_error(422, "bad_location", "Choose the places from the list")
    a = DisasterAlert(type=body.type, severity=body.severity, status=AlertStatus.confirmed, title=" ".join(body.title.split()),
                      summary=body.summary, reported_figures={k: v for k, v in body.figures.items() if v and v > 0},
                      started_at=datetime.now(timezone.utc), confirmed_by=admin.id, confirmed_at=datetime.now(timezone.utc))
    a.locations = locs
    db.add(a)
    db.flush()
    suggest_alert_needs(db, a)
    db.commit()
    recompute(db)
    return alert_out(db, a)


@router.post("/admin/alerts/{alert_id}/status", response_model=AlertOut)
def set_status(alert_id: uuid.UUID, body: StatusIn, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    a = _get(db, alert_id)
    a.status = AlertStatus(body.status)
    if a.status == AlertStatus.confirmed:
        a.confirmed_by, a.confirmed_at = admin.id, datetime.now(timezone.utc)
        if not a.needs:
            suggest_alert_needs(db, a)
    db.commit()
    recompute(db)   # confirmed alerts count fully in "needs by area"; dismissed / handled ones drop out
    return alert_out(db, a)


@router.put("/admin/alerts/{alert_id}/needs", response_model=AlertOut)
def set_needs(alert_id: uuid.UUID, body: list[NeedIn], _: User = Depends(admin_only), db: Session = Depends(get_db)):
    """Replace the 'what is needed' table. Categories left out are removed."""
    a = _get(db, alert_id)
    valid = {c.id for c in db.scalars(select(Category))}
    if any(n.category_id not in valid for n in body):
        raise api_error(422, "bad_category", "Unknown category")
    keep = {n.category_id: n for n in body}
    for n in list(a.needs):
        if n.category_id not in keep:
            a.needs.remove(n)
    have = {n.category_id: n for n in a.needs}
    for cid, n in keep.items():
        if cid in have:
            have[cid].quantity_needed = n.quantity_needed
        else:
            a.needs.append(AlertNeed(category_id=cid, quantity_needed=n.quantity_needed))
    db.commit()
    return alert_out(db, a)


# ---------- data sources ----------

class SourceOut(BaseModel):
    kind: SourceKind
    name: str
    is_enabled: bool
    every_minutes: Optional[int]
    last_run_at: Optional[datetime]
    last_status: Optional[str]
    can_run: bool


RUNNABLE = {SourceKind.gdacs, SourceKind.hdx_hapi, SourceKind.web_search, SourceKind.reliefweb, SourceKind.ai_needs}


def can_run(kind: SourceKind) -> bool:
    if kind == SourceKind.reliefweb:
        return bool(settings.RELIEFWEB_APPNAME)
    if kind in (SourceKind.web_search, SourceKind.ai_needs):
        return llm.available()
    return kind in RUNNABLE


@router.get("/admin/sources", response_model=list[SourceOut])
def sources(_: User = Depends(admin_only), db: Session = Depends(get_db)):
    return [SourceOut(kind=s.kind, name=s.name, is_enabled=s.is_enabled, every_minutes=s.every_minutes, last_run_at=s.last_run_at,
                      last_status=s.last_status, can_run=can_run(s.kind))
            for s in db.scalars(select(Source).order_by(Source.id))]


@router.post("/admin/sources/{kind}/run")
def run(kind: SourceKind, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    """Fetch now. The web scan asks Claude to search the news (takes up to a minute, costs a few cents)."""
    if not can_run(kind):
        raise api_error(422, "not_runnable", "This source is not set up yet" if kind == SourceKind.reliefweb else "This source is not automatic yet")
    ok, status = run_source(db, kind)
    return {"ok": ok, "status": status}
