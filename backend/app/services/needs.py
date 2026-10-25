"""Need engine (Phase 6): one need level per area and category, with the reasons behind it.

Level 0 none · 1 some · 2 high · 3 urgent, from a score 0-100 (the highest signal, plus 5 for each other
strong signal). Signals:

  IPC Phase 3+ share (food, grocery)      >=30% 85 · >=20% 65 · >=10% 40
  Staple price rise over ~3 months         >=20% 60 · >=10% 45   (grocery; food a bit lower)
  Poverty headcount (province)             >=40% 40 · >=25% 25   (grocery, food, clothes, school, hygiene)
  Disaster alert in the area (30 days)     severe 90 · moderate 65 · watch 40; unconfirmed x0.7
  Open requests at a distribution point    40, or 60 if 50+ items asked for
"""

import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AlertNeed, Category, DisasterAlert, DistributionPoint, Location, NeedIndicator, NeedLevel, PointRequest
from app.models.enums import AlertSeverity, AlertStatus, AlertType, RequestStatus
from app.services.locations import descendant_ids

LEVEL_NAMES = ["none", "some", "high", "urgent"]

ALERT_CATEGORIES: dict[AlertType, list[str]] = {
    AlertType.flood: ["emergency_relief", "grocery_ration", "hygiene", "blankets", "clothes", "food"],
    AlertType.earthquake: ["emergency_relief", "blankets", "winter_support", "household", "grocery_ration"],
    AlertType.cyclone: ["emergency_relief", "grocery_ration", "hygiene", "household"],
    AlertType.drought: ["grocery_ration", "food", "hygiene"],
    AlertType.heatwave: ["hygiene", "food"],
    AlertType.cold_wave: ["blankets", "winter_support", "clothes"],
    AlertType.heavy_rain: ["emergency_relief", "hygiene", "household", "blankets"],
    AlertType.other: ["emergency_relief"],
}
# Items per affected family, to suggest "what is needed" from reported figures (the admin can edit)
PER_FAMILY: dict[AlertType, dict[str, float]] = {
    AlertType.flood: {"grocery_ration": 1, "hygiene": 1, "blankets": 2, "emergency_relief": 0.5, "clothes": 1},
    AlertType.earthquake: {"emergency_relief": 1, "blankets": 3, "grocery_ration": 1, "household": 1},
    AlertType.cyclone: {"grocery_ration": 1, "hygiene": 1, "emergency_relief": 0.5},
    AlertType.drought: {"grocery_ration": 1, "hygiene": 1},
    AlertType.heatwave: {"hygiene": 1},
    AlertType.cold_wave: {"blankets": 2, "winter_support": 1},
    AlertType.heavy_rain: {"hygiene": 1, "blankets": 1, "household": 0.5},
    AlertType.other: {"emergency_relief": 1},
}
PEOPLE_PER_FAMILY = 6
ALERT_SCORE = {AlertSeverity.severe: 90, AlertSeverity.moderate: 65, AlertSeverity.watch: 40}


# ---------- pure scoring rules (unit-tested) ----------

def score_ipc(share: float) -> int:
    return 85 if share >= 0.30 else 65 if share >= 0.20 else 40 if share >= 0.10 else 0


def score_price(change: float) -> int:
    return 60 if change >= 0.20 else 45 if change >= 0.10 else 0


def score_poverty(share: float) -> int:
    return 40 if share >= 0.40 else 25 if share >= 0.25 else 0


def score_alert(severity: AlertSeverity, confirmed: bool) -> int:
    return round(ALERT_SCORE[severity] * (1 if confirmed else 0.7))


def score_requests(quantity: int) -> int:
    return 60 if quantity >= 50 else 40


def level_of(score: float) -> int:
    return 3 if score >= 80 else 2 if score >= 55 else 1 if score >= 30 else 0


def combine(signals: list[tuple[int, dict]]) -> tuple[float, int, list[dict]]:
    """(score, level, reasons) from (points, reason) pairs."""
    signals = sorted((s for s in signals if s[0] > 0), key=lambda s: -s[0])
    if not signals:
        return 0, 0, []
    score = min(100, signals[0][0] + 5 * sum(1 for p, _ in signals[1:] if p >= 25))
    return score, level_of(score), [dict(r, points=p) for p, r in signals[:4]]


def families(figures: dict[str, Any]) -> Optional[int]:
    if figures.get("families_affected"):
        return int(figures["families_affected"])
    if figures.get("people_affected"):
        return max(1, round(figures["people_affected"] / PEOPLE_PER_FAMILY))
    if figures.get("houses_damaged"):
        return int(figures["houses_damaged"])
    return None


# ---------- database ----------

def _slug_ids(db: Session) -> dict[str, int]:
    return {c.slug: c.id for c in db.scalars(select(Category))}


def suggest_alert_needs(db: Session, alert: DisasterAlert) -> None:
    """Fill the alert's 'what is needed' rows: categories for its type, quantities from reported figures.
    Quantities an admin already set are kept."""
    ids = _slug_ids(db)
    fam = families(alert.reported_figures or {})
    have = {n.category_id: n for n in alert.needs}
    for slug in ALERT_CATEGORIES.get(alert.type, []):
        cid = ids.get(slug)
        if cid is None:
            continue
        per = PER_FAMILY.get(alert.type, {}).get(slug)
        qty = round(fam * per) if (fam and per) else None
        if cid not in have:
            alert.needs.append(AlertNeed(category_id=cid, quantity_needed=qty))
        elif have[cid].quantity_needed is None and qty:
            have[cid].quantity_needed = qty


def recompute(db: Session) -> int:
    """Rebuild the need_levels table from all signals. Returns the number of (area, category) rows."""
    ids = _slug_ids(db)
    names = {l.id: l.name for l in db.scalars(select(Location))}
    sig: dict[tuple[uuid.UUID, int], list[tuple[int, dict]]] = defaultdict(list)

    def add(loc: uuid.UUID, slug: str, pts: int, reason: dict, adjust: int = 0):
        if slug in ids and pts + adjust > 0:
            sig[(loc, ids[slug])].append((pts + adjust, reason))

    for ind in db.scalars(select(NeedIndicator)):
        when = ind.period_end.strftime("%b %Y") if ind.period_end else None
        if ind.indicator == "ipc_phase3plus_share":
            r = {"why": f"IPC Phase 3+ (crisis or worse) for {ind.value:.0%} of people", "source": "IPC via HDX", "date": when}
            add(ind.location_id, "food", score_ipc(ind.value), r)
            add(ind.location_id, "grocery_ration", score_ipc(ind.value), r)
        elif ind.indicator == "price_change_3m":
            meta = ind.meta or {}
            r = {"why": f"{meta.get('commodity', 'Staple')} price up {ind.value:.0%} in 3 months ({meta.get('market', '')})".replace(" ()", ""),
                 "source": "WFP food prices via HDX", "date": when}
            add(ind.location_id, "grocery_ration", score_price(ind.value), r)
            add(ind.location_id, "food", score_price(ind.value), r, adjust=-10)
        elif ind.indicator == "poverty_headcount":
            r = {"why": f"{ind.value:.0%} of people multidimensionally poor", "source": "Poverty rate via HDX", "date": when}
            for slug in ("grocery_ration", "food", "clothes", "school_supplies", "hygiene"):
                add(ind.location_id, slug, score_poverty(ind.value), r)

    since = datetime.now(timezone.utc) - timedelta(days=30)
    alerts = db.scalars(select(DisasterAlert).where(DisasterAlert.status.in_([AlertStatus.confirmed, AlertStatus.unconfirmed]),
                                                    DisasterAlert.created_at >= since))
    for a in alerts:
        confirmed = a.status == AlertStatus.confirmed
        r = {"why": f"{a.title}{'' if confirmed else ' (not confirmed yet)'}", "source": "Disaster alert",
             "date": (a.started_at or a.created_at).strftime("%d %b %Y"), "alert_id": str(a.id)}
        for loc in a.locations:
            for slug in ALERT_CATEGORIES.get(a.type, []):
                add(loc.id, slug, score_alert(a.severity, confirmed), r)

    by_id = {c.id: c.slug for c in db.scalars(select(Category))}
    reqs: dict[tuple, list] = defaultdict(lambda: [0, 0, None])
    for req, point in db.execute(select(PointRequest, DistributionPoint).join(DistributionPoint, DistributionPoint.id == PointRequest.point_id)
                                 .where(PointRequest.status == RequestStatus.open)):
        k = (point.location_id, req.category_id)
        reqs[k][0] += req.quantity
        reqs[k][1] += 1
        reqs[k][2] = point.name
    for (loc, cid), (qty, n, pname) in reqs.items():
        r = {"why": f"People at {pname} asked for {qty}", "source": "Distribution point requests", "date": None}
        add(loc, by_id.get(cid, ""), score_requests(qty), r)

    db.execute(delete(NeedLevel))
    now = datetime.now(timezone.utc)
    count = 0
    for (loc, cid), signals in sig.items():
        score, level, reasons = combine(signals)
        if level == 0:
            continue
        for r in reasons:
            r.setdefault("place", names.get(loc))
        db.add(NeedLevel(location_id=loc, category_id=cid, level=level, score=score, reasons=reasons, computed_at=now))
        count += 1
    db.commit()
    return count


def area_needs(db: Session, parent_id: Optional[uuid.UUID]) -> dict[str, Any]:
    """Needs for a place and each place under it (provinces when parent_id is None).
    Each row shows, per category, the highest level found anywhere inside that place."""
    cats = {c.id: c.name for c in db.scalars(select(Category))}

    def summary(loc_ids: list[uuid.UUID]) -> list[dict]:
        best: dict[int, NeedLevel] = {}
        for nl in db.scalars(select(NeedLevel).where(NeedLevel.location_id.in_(loc_ids))):
            if nl.category_id not in best or nl.score > best[nl.category_id].score:
                best[nl.category_id] = nl
        rows = [{"category_id": cid, "name": cats.get(cid, "?"), "level": nl.level, "level_name": LEVEL_NAMES[nl.level],
                 "score": round(nl.score), "reasons": nl.reasons} for cid, nl in best.items()]
        return sorted(rows, key=lambda r: (-r["score"], r["category_id"]))

    children = db.scalars(select(Location).where(Location.parent_id == parent_id if parent_id else Location.parent_id.is_(None))
                          .order_by(Location.name)).all()
    out_children = []
    for c in children:
        sub = descendant_ids(db, c.id)
        needs = summary(sub)
        out_children.append({"id": str(c.id), "name": c.name, "level": c.level.value, "lat": c.lat, "lng": c.lng,
                             "has_children": len(sub) > 1, "max_level": max((n["level"] for n in needs), default=0),
                             "needs": needs})
    out_children.sort(key=lambda r: (-r["max_level"], -sum(n["score"] for n in r["needs"][:3]), r["name"]))
    parent = db.get(Location, parent_id) if parent_id else None
    computed = db.scalar(select(NeedLevel.computed_at).limit(1))
    return {
        "place": {"id": str(parent.id), "name": parent.name, "level": parent.level.value, "parent_id": str(parent.parent_id) if parent.parent_id else None} if parent else None,
        "summary": summary(descendant_ids(db, parent_id)) if parent_id else None,
        "children": out_children,
        "computed_at": computed,
    }
