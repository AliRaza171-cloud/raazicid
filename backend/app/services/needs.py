"""Need engine (Phase 6): one need level per area and category, with the reasons behind it.

Level 0 none · 1 some · 2 high · 3 urgent, from a score 0-100 (the highest signal, plus 5 for each other
strong signal). Signals:

  IPC Phase 3+ share (food, grocery)      >=30% 85 · >=20% 65 · >=10% 40
  Staple price rise over ~3 months         >=20% 60 · >=10% 45   (grocery; food a bit lower)
  Poverty headcount (province)             >=40% 40 · >=25% 25   (grocery, food, clothes, school, hygiene)
  Disaster alert in the area (30 days)     severe 90 · moderate 65 · watch 40; unconfirmed x0.7
  Open requests at a distribution point    40, or 60 if 50+ items asked for
  People in need (OCHA, by sector)         share >=40% 85 · >=25% 65 · >=10% 45; or 500k+ 75 · 100k+ 60 · 20k+ 40
  Rainfall vs long-term average (3 months) +100% 50 · +60% 40 (flood risk) · -60% 50 · -40% 35 (drought risk)
  Displaced people living here (IOM DTM)   100k+ 70 · 20k+ 60 · 5k+ 45 · 1k+ 30  (relief, rations, food, hygiene, blankets, household;
                                           alone it reaches "high": "urgent" needs a second source)
  AI web scan of the last 90 days          urgent 70 · high 55 · some 35 (with its source link)
  Report reader (needs stated in library   same points, with the report title, page and quote
  reports: ReliefWeb, uploads, links)      (+10 for both when no aid has reached the people yet)

Data more than a year old counts 0.75 (poverty, which changes slowly, keeps 0.75) and its reason says
"(old_year: 2025, shown as "old" in the admin)". Data older than NEED_DATA_MAX_YEARS (default 2) is not used at all.

Long-term deprivation tables (PSLM, HIES, DTM sheets an admin uploads, stored as "dep:*") never change the level:
they are shown on their own, see services/deprivation.py.

3W (who works where, OCHA) does not change the level: it marks a place "neglected" for a category when the need
is high or urgent and no organisation works on it there.
"""

import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (AlertNeed, Category, DisasterAlert, DistributionPoint, Location, NeedIndicator, NeedLevel, PointRequest,
                        Report)
from app.models.enums import AlertSeverity, AlertStatus, AlertType, ReportStatus, RequestStatus
from app.services.locations import descendant_ids
from app.services.sources.ai_needs import shows_gap
from app.services.sources.hapi_un import category_sectors, sector_categories

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


def score_pin(people: float, share: Optional[float]) -> int:
    if share is not None:
        return 85 if share >= 0.40 else 65 if share >= 0.25 else 45 if share >= 0.10 else 0
    return 75 if people >= 500_000 else 60 if people >= 100_000 else 40 if people >= 20_000 else 0


RAIN_CATEGORIES = {"wet": ["emergency_relief", "hygiene", "household", "blankets"], "dry": ["food", "grocery_ration", "hygiene"]}


def score_rain(anomaly_pct: float) -> tuple[int, Optional[str]]:
    """(points, "wet" | "dry") from rainfall compared with the long-term average, in percent."""
    if anomaly_pct >= 100:
        return 50, "wet"
    if anomaly_pct >= 60:
        return 40, "wet"
    if anomaly_pct <= -60:
        return 50, "dry"
    if anomaly_pct <= -40:
        return 35, "dry"
    return 0, None


# Measures that change slowly: old figures still say a lot, so they lose at most a quarter of their weight
IDP_CATEGORIES = ["emergency_relief", "grocery_ration", "food", "hygiene", "blankets", "household"]


def score_idps(people: float) -> int:
    """Displaced people living in a place (IOM DTM)."""
    return 70 if people >= 100_000 else 60 if people >= 20_000 else 45 if people >= 5_000 else 30 if people >= 1_000 else 0


SLOW_CHANGING = {"poverty_headcount"}
AI_POINTS = {3: 70, 2: 55, 1: 35}   # AI web scan alone can reach "high"; "urgent" needs a second source


def score_ai(level: float) -> int:
    return AI_POINTS.get(int(level), 0)


def freshness(period_end: Optional[date], today: Optional[date] = None) -> str:
    """'new' (last 3 months), 'recent' (this year) or 'old' (over a year). Alerts and requests are always new."""
    if period_end is None:
        return "new"
    days = ((today or datetime.now(timezone.utc).date()) - period_end).days
    return "new" if days <= 92 else "recent" if days <= 366 else "old"


def strength(points: float) -> str:
    """How much one reason weighs, in words: 'very strong' alone makes a need urgent, 'strong' high, 'medium' some."""
    return "very strong" if points >= 80 else "strong" if points >= 55 else "medium" if points >= 30 else "weak"


def too_old(period_end: Optional[date], today: Optional[date] = None) -> bool:
    """Data older than NEED_DATA_MAX_YEARS is left out of the need levels."""
    if period_end is None:
        return False
    today = today or datetime.now(timezone.utc).date()
    return (today - period_end).days > settings.NEED_DATA_MAX_YEARS * 365


def age_factor(period_end: Optional[date], today: Optional[date] = None) -> tuple[float, Optional[str]]:
    """(weight, year label if old). Up to 1 year old: full weight; up to 2 years: 0.75; older: 0.5."""
    if period_end is None:
        return 1.0, None
    today = today or datetime.now(timezone.utc).date()
    days = (today - period_end).days
    if days <= 365:
        return 1.0, None
    return (0.75 if days <= 730 else 0.5), str(period_end.year)


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
    ids_to_slug = {v: k for k, v in ids.items()}
    names = {l.id: l.name for l in db.scalars(select(Location))}
    sig: dict[tuple[uuid.UUID, int], list[tuple[int, dict]]] = defaultdict(list)

    age = {"factor": 1.0, "old": None, "end": None}   # set per indicator: older data counts less

    def add(loc: uuid.UUID, slug: str, pts: int, reason: dict, adjust: int = 0):
        pts = round((pts + adjust) * age["factor"])
        if slug in ids and pts > 0:
            reason = {**reason, "fresh": freshness(age["end"]), "strength": strength(pts)}
            if age["old"]:
                reason.update(old=True, old_year=age["old"])
            sig[(loc, ids[slug])].append((pts, reason))

    archived = set(db.scalars(select(Report.id).where(Report.status == ReportStatus.archived)))
    for ind in db.scalars(select(NeedIndicator)):
        if ind.indicator == "orgs_present" or ind.indicator.startswith("dep:"):
            continue   # who works where, and long-term deprivation tables: not need signals
        if too_old(ind.period_end):
            continue   # e.g. the 2018 poverty survey: too old to say what people need today
        when = ind.period_end.strftime("%b %Y") if ind.period_end else None
        age["factor"], age["old"] = age_factor(ind.period_end)
        age["end"] = ind.period_end
        if ind.indicator in SLOW_CHANGING:
            age["factor"] = max(age["factor"], 0.75)   # poverty changes over years, not months
        if ind.indicator == "report_need":
            meta = ind.meta or {}
            if ind.report_id in archived or not shows_gap(meta.get("why") or "", meta.get("unmet") or ""):
                continue
            reached = meta.get("reached") or "unknown"
            why = (meta.get("why") or "Reported need").rstrip(".") + "." + {"none": " No aid has reached them yet.",
                                                          "partial": " Some aid has arrived, not enough."}.get(reached, "")
            page = f", page {meta['page']}" if meta.get("page") else ""
            r = {"why": why, "source": f"Report · {meta.get('title') or 'report'}{page}"[:160], "quote": meta.get("unmet") or None,
                 "date": ind.period_end.strftime("%d %b %Y") if ind.period_end else None, "url": meta.get("url"),
                 "report_id": str(ind.report_id) if ind.report_id else None, "reached": reached}
            add(ind.location_id, ids_to_slug.get(ind.category_id, ""), score_ai(ind.value) + (10 if reached == "none" else 0), r)
            continue
        if ind.indicator == "ai_need":
            if ind.period_end and (datetime.now(timezone.utc).date() - ind.period_end).days > 120:
                continue   # AI-found news expires; run the scan again for fresh evidence
            meta = ind.meta or {}
            src = (meta.get("sources") or [{}])[0]
            if not shows_gap(meta.get("why") or "", meta.get("unmet") or ""):
                continue   # an older scan's "aid handed out" finding: not an unmet need
            reached = meta.get("reached") or "unknown"
            why = meta.get("why") or "Reported need"
            if reached == "none":
                why += " No aid has reached them yet."
            elif reached == "partial":
                why += " Some aid has arrived, not enough."
            r = {"why": why, "source": f"AI web scan · {src.get('title') or 'news'}"[:120], "quote": meta.get("unmet") or None,
                 "date": ind.period_end.strftime("%d %b %Y") if ind.period_end else None, "url": src.get("url"), "reached": reached}
            # Nobody has reached them: +10, the people RAAZICID should go to first
            add(ind.location_id, ids_to_slug.get(ind.category_id, ""), score_ai(ind.value) + (10 if reached == "none" else 0), r)
            continue
        if ind.indicator == "ipc_phase3plus_share":
            people = (ind.meta or {}).get("people")
            count = f" (about {int(people):,} people)" if people else ""
            r = {"why": f"{ind.value:.0%} of people do not have enough food{count}. This is the IPC 'crisis' level or worse.",
                 "source": "IPC food security data (via HDX)", "date": when}
            add(ind.location_id, "food", score_ipc(ind.value), r)
            add(ind.location_id, "grocery_ration", score_ipc(ind.value), r)
        elif ind.indicator == "price_change_3m":
            meta = ind.meta or {}
            market = f" at {meta['market']} market" if meta.get("market") else ""
            r = {"why": f"The price of {str(meta.get('commodity') or 'basic food').lower()} went up {ind.value:.0%} in 3 months{market}. "
                        "Families can buy less.", "source": "WFP market prices (via HDX)", "date": when}
            add(ind.location_id, "grocery_ration", score_price(ind.value), r)
            add(ind.location_id, "food", score_price(ind.value), r, adjust=-10)
        elif ind.indicator == "people_in_need":
            meta = ind.meta or {}
            share = meta.get("share")
            pts = score_pin(ind.value, share)
            sector = meta.get("sector") or "all sectors"
            people = f"{int(ind.value):,} people" + (f" ({share:.0%} of everyone here)" if share else "")
            r = {"why": f"{people} need help with {sector.lower()}, says the UN.", "source": "UN people-in-need count (OCHA, via HDX)",
                 "date": when}
            for slug in sector_categories(sector):
                add(ind.location_id, slug, pts, r)
        elif ind.indicator == "rainfall_anomaly_pct":
            pts, kind = score_rain(ind.value)
            if kind:
                word, risk = ("more", "Floods may happen.") if kind == "wet" else ("less", "Crops and water may run short (drought).")
                r = {"why": f"It rained {abs(ind.value):.0f}% {word} than normal in the last 3 months. {risk}",
                     "source": "WFP rainfall data (via HDX)", "date": when}
                for slug in RAIN_CATEGORIES[kind]:
                    add(ind.location_id, slug, pts, r)
        elif ind.indicator == "idps_present":
            meta = ind.meta or {}
            ops = ", ".join(meta.get("operations") or []) or "DTM"
            r = {"why": f"{int(ind.value):,} people who had to leave their homes live here ({ops}).",
                 "source": "IOM displacement data (DTM, via HDX)", "date": when}
            for slug in IDP_CATEGORIES:
                add(ind.location_id, slug, score_idps(ind.value), r)
        elif ind.indicator == "poverty_headcount":
            r = {"why": f"{ind.value:.0%} of people are poor (short of money, schooling or health care).",
                 "source": "Poverty survey (via HDX)", "date": when}
            for slug in ("grocery_ration", "food", "clothes", "school_supplies", "hygiene"):
                add(ind.location_id, slug, score_poverty(ind.value), r)

    age["factor"], age["old"], age["end"] = 1.0, None, None   # alerts and requests are always recent
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
        r = {"why": f"People at our point {pname} asked for {qty} of these.", "source": "Request at our distribution point", "date": None}
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

    slugs = {c.id: c.slug for c in db.scalars(select(Category))}
    has_3w = db.scalar(select(NeedIndicator.id).where(NeedIndicator.indicator == "orgs_present").limit(1)) is not None

    def who_works(loc_ids: list[uuid.UUID]) -> dict[str, list[str]]:
        sectors: dict[str, set] = defaultdict(set)
        for ind in db.scalars(select(NeedIndicator).where(NeedIndicator.indicator == "orgs_present", NeedIndicator.location_id.in_(loc_ids))):
            for sector, orgs in ((ind.meta or {}).get("sectors") or {}).items():
                sectors[sector] |= set(orgs)
        return {k: sorted(v) for k, v in sorted(sectors.items())}

    children = db.scalars(select(Location).where(Location.parent_id == parent_id if parent_id else Location.parent_id.is_(None))
                          .order_by(Location.name)).all()
    out_children = []
    for c in children:
        sub = descendant_ids(db, c.id)
        needs = summary(sub)
        works = who_works(sub) if has_3w else {}
        neglected = [n["name"] for n in needs if has_3w and n["level"] >= 2
                     and not category_sectors(slugs.get(n["category_id"], ""), list(works))]
        out_children.append({"id": str(c.id), "name": c.name, "level": c.level.value, "lat": c.lat, "lng": c.lng,
                             "has_children": len(sub) > 1, "max_level": max((n["level"] for n in needs), default=0),
                             "needs": needs, "orgs": len(set().union(*map(set, works.values()))) if works else 0,
                             "who_works": works, "neglected": neglected})
    out_children.sort(key=lambda r: (-r["max_level"], -sum(n["score"] for n in r["needs"][:3]), r["name"]))
    parent = db.get(Location, parent_id) if parent_id else None
    computed = db.scalar(select(NeedLevel.computed_at).limit(1))
    return {
        "place": {"id": str(parent.id), "name": parent.name, "level": parent.level.value, "parent_id": str(parent.parent_id) if parent.parent_id else None} if parent else None,
        "summary": summary(descendant_ids(db, parent_id)) if parent_id else None,
        "children": out_children,
        "computed_at": computed,
        "has_3w": has_3w,
    }
