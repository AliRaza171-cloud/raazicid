"""HDX HAPI (Humanitarian Data Exchange): IPC food insecurity per district, food prices, poverty per province.

Needs only an app identifier made from your email (HDX_EMAIL). Districts that are not in our places yet
(e.g. Tharparkar, Kech) are added as regions under their province, matched by the HDX admin2 code.
"""

import base64
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Optional

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Location, NeedIndicator
from app.models.enums import LocationLevel, SourceKind
from app.services.gazetteer import Place, find_places, load_places

ROOT = "https://hapi.humdata.org/api/v2/"
BASE = ROOT + "food-security-nutrition-poverty/"
STAPLES = {"cereals and tubers", "pulses and nuts", "oil and fats"}
TYPE_ORDER = {"current": 0, "first projection": 1, "second projection": 2}
GROCERY_ID = 2


def app_identifier() -> Optional[str]:
    if settings.HDX_APP_IDENTIFIER:
        return settings.HDX_APP_IDENTIFIER
    if settings.HDX_EMAIL:
        return base64.b64encode(f"RAAZICID-FYP:{settings.HDX_EMAIL}".encode()).decode()
    return None


def get_all(path: str, app_id: str, root: str = BASE, pakistan: bool = True, **params) -> list[dict[str, Any]]:
    """Every row of a HAPI endpoint, 1,000 at a time. pakistan=False for endpoints without location_code (refugees)."""
    rows, offset = [], 0
    where = {"location_code": "PAK"} if pakistan else {}
    while offset <= 50000:
        res = httpx.get(root + path, timeout=60, params={
            "app_identifier": app_id, **where, "output_format": "json", "limit": 1000, "offset": offset, **params})
        res.raise_for_status()
        page = res.json().get("data", [])
        rows += page
        if len(page) < 1000:
            break
        offset += 1000
    return rows


def _d(v: Any) -> Optional[date]:
    try:
        return datetime.fromisoformat(str(v)[:10]).date()
    except (TypeError, ValueError):
        return None


def ipc_latest(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Newest IPC Phase 3+ share per district (current analysis preferred over projections)."""
    best: dict[str, dict] = {}
    for r in rows:
        if str(r.get("ipc_phase")) != "3+" or not r.get("admin2_name") or r.get("population_fraction_in_phase") is None:
            continue
        key = r.get("admin2_code") or r["admin2_name"]
        rank = (_d(r.get("reference_period_end")) or date.min, -TYPE_ORDER.get(str(r.get("ipc_type")), 9))
        if key not in best or rank > best[key]["_rank"]:
            best[key] = {"_rank": rank, "admin1_name": r.get("admin1_name"), "admin2_name": r["admin2_name"],
                         "admin2_code": r.get("admin2_code"), "share": float(r["population_fraction_in_phase"]),
                         "period_start": _d(r.get("reference_period_start")), "period_end": _d(r.get("reference_period_end")),
                         "ipc_type": r.get("ipc_type"), "people": r.get("population_in_phase")}
    return [{k: v for k, v in b.items() if k != "_rank"} for b in best.values()]


def price_changes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per market: the biggest staple price rise over about 3 months (retail prices)."""
    series: dict[tuple, list[tuple[date, float]]] = defaultdict(list)
    info: dict[str, dict] = {}
    for r in rows:
        if str(r.get("commodity_category", "")).lower() not in STAPLES or str(r.get("price_type", "")).lower() != "retail":
            continue
        d, price = _d(r.get("reference_period_start")), r.get("price")
        if d is None or price in (None, 0):
            continue
        m = r.get("market_name") or r.get("admin2_name") or r.get("admin1_name")
        series[(m, r.get("commodity_name"), r.get("unit"))].append((d, float(price)))
        info[m] = {"market_name": m, "admin1_name": r.get("admin1_name"), "admin2_name": r.get("admin2_name")}
    out: dict[str, dict] = {}
    for (m, commodity, _), pts in series.items():
        pts.sort()
        d1, p1 = pts[-1]
        older = [(d, p) for d, p in pts if 60 <= (d1 - d).days <= 120]
        if not older:
            continue
        d0, p0 = min(older, key=lambda x: abs((d1 - x[0]).days - 90))
        change = p1 / p0 - 1
        if m not in out or change > out[m]["change"]:
            out[m] = {**info[m], "change": round(change, 4), "commodity": commodity, "from": d0, "to": d1}
    return list(out.values())


def poverty_latest(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict] = {}
    for r in rows:
        if not r.get("admin1_name") or r.get("headcount_ratio") is None:
            continue
        v = float(r["headcount_ratio"])
        v = v / 100 if v > 1 else v
        d = _d(r.get("reference_period_end")) or date.min
        if r["admin1_name"] not in best or d > best[r["admin1_name"]]["period_end"]:
            best[r["admin1_name"]] = {"admin1_name": r["admin1_name"], "share": v, "period_end": d,
                                      "period_start": _d(r.get("reference_period_start"))}
    return list(best.values())


def _province(name: Optional[str], places: list[Place]) -> Optional[Place]:
    if not name:
        return None
    hits = [p for p in find_places(name, places) if p.level == "province"]
    return hits[0] if hits else next((p for p in places if p.level == "province" and p.name.lower() == name.lower()), None)


def _district(db: Session, province: Place, name: str, code: Optional[str], places: list[Place]) -> Location:
    """Existing place for an HDX district, or a new region under its province."""
    if code:
        loc = db.scalar(select(Location).where(Location.admin_code == code))
        if loc:
            return loc
    for p in places:
        if p.name.lower() == name.lower() and p.level in ("city", "region"):
            loc = db.get(Location, p.id)
            if code and not loc.admin_code:
                loc.admin_code = code
            return loc
    loc = Location(name=name, level=LocationLevel.region, parent_id=province.id, admin_code=code)
    db.add(loc)
    db.flush()
    places.append(Place(loc.id, loc.name, "region", province.id, None, None))
    return loc


def _where(db: Session, r: dict, places: list[Place]) -> Optional[Location]:
    """Our place for a HAPI row: the district (added under its province if new), or the province."""
    prov = _province(r.get("admin1_name"), places)
    if prov is None:
        return None
    if r.get("admin2_name"):
        return _district(db, prov, r["admin2_name"], r.get("admin2_code"), places)
    return db.get(Location, prov.id)


def sync_un(db: Session, un: dict, source_id: int, places: list[Place]) -> list[str]:
    """3W, people in need and rainfall as indicators; refugee totals as a library report. Returns status parts."""
    parts = []
    n = 0
    for r in un.get("presence") or []:
        loc = _where(db, r, places)
        if loc is None:
            continue
        db.add(NeedIndicator(location_id=loc.id, indicator="orgs_present", value=r["orgs"], source_id=source_id,
                             period_end=r["period_end"], meta={"sectors": r["sectors"]}))
        n += 1
    parts.append(f"3W {n} places" if n else "3W: none for Pakistan")
    n = 0
    for r in un.get("pin") or []:
        loc = _where(db, r, places)
        if loc is None:
            continue
        db.add(NeedIndicator(location_id=loc.id, indicator="people_in_need", value=r["people"], source_id=source_id,
                             period_start=r["period_start"], period_end=r["period_end"],
                             meta={"sector": r["sector"], "share": r["share"]}))
        n += 1
    parts.append(f"people in need {n}" if n else "people in need: none published for Pakistan")
    n = 0
    for r in un.get("rain") or []:
        loc = _where(db, r, places)
        if loc is None:
            continue
        db.add(NeedIndicator(location_id=loc.id, indicator="rainfall_anomaly_pct", value=r["anomaly_pct"], source_id=source_id,
                             period_start=r["period_start"], period_end=r["period_end"],
                             meta={"rainfall": r["rainfall"], "average": r["average"], "period": r["period"]}))
        n += 1
    parts.append(f"rainfall {n} districts" if n else "rainfall: none")
    n, newest = 0, None
    for r in un.get("idps") or []:
        loc = _where(db, r, places)
        if loc is None:
            continue
        db.add(NeedIndicator(location_id=loc.id, indicator="idps_present", value=r["people"], source_id=source_id,
                             period_start=r["period_start"], period_end=r["period_end"],
                             meta={"operations": r["operations"], "round": r["round"]}))
        n += 1
        newest = max(newest or r["period_end"], r["period_end"])
    parts.append(f"displaced people (IOM DTM) {n} places, latest {newest:%b %Y}" if n else "displaced people (IOM DTM): none for Pakistan")
    return parts


def sync(db: Session, ipc: list[dict], prices: list[dict], poverty: list[dict], source_id: int, un: Optional[dict] = None) -> str:
    places = load_places(db)
    db.execute(delete(NeedIndicator).where(NeedIndicator.source_id == source_id))
    n_ipc = n_price = n_pov = 0
    for r in ipc:
        prov = _province(r["admin1_name"], places)
        if prov is None:
            continue
        loc = _district(db, prov, r["admin2_name"], r.get("admin2_code"), places)
        db.add(NeedIndicator(location_id=loc.id, indicator="ipc_phase3plus_share", value=r["share"], source_id=source_id,
                             period_start=r["period_start"], period_end=r["period_end"],
                             meta={"ipc_type": r["ipc_type"], "people": r["people"]}))
        n_ipc += 1
    for r in prices:
        hits = find_places(r["market_name"] or "", places) or find_places(r.get("admin2_name") or "", places)
        loc_id = hits[0].id if hits else getattr(_province(r["admin1_name"], places), "id", None)
        if loc_id is None:
            continue
        db.add(NeedIndicator(location_id=loc_id, category_id=GROCERY_ID, indicator="price_change_3m", value=r["change"],
                             source_id=source_id, period_start=r["from"], period_end=r["to"],
                             meta={"market": r["market_name"], "commodity": r["commodity"]}))
        n_price += 1
    for r in poverty:
        prov = _province(r["admin1_name"], places)
        if prov is None:
            continue
        db.add(NeedIndicator(location_id=prov.id, indicator="poverty_headcount", value=r["share"], source_id=source_id,
                             period_start=r["period_start"], period_end=r["period_end"]))
        n_pov += 1
    un_parts = sync_un(db, un, source_id, places) if un is not None else []
    db.commit()
    if un and un.get("refugees"):
        un_parts.append(save_refugees(db, un["refugees"]))
    return "; ".join([f"IPC {n_ipc} districts, prices {n_price} markets, poverty {n_pov} provinces", *un_parts])


def save_refugees(db: Session, r: dict) -> str:
    """UNHCR totals become a short report in the library, so the need finder can quote them."""
    from app.services.rag.ingest import IngestError, add_report
    from app.services.sources.hapi_un import refugee_text
    try:
        _, created = add_report(db, kind=SourceKind.hdx_hapi, title=f"UNHCR: refugees and asylum-seekers in Pakistan ({r['period_end']:%Y})",
                                pages=[(None, refugee_text(r))], publisher="UNHCR via HDX", external_id=f"unhcr-pak-{r['period_end']}",
                                url="https://data.humdata.org/organization/unhcr")
    except IngestError as e:
        db.rollback()
        return f"refugees: {e}"
    return f"refugees {sum(r['groups'].values()):,} (UNHCR)" + ("" if created else ", already in library")


def fetch_and_sync(db: Session, source_id: int) -> str:
    app_id = app_identifier()
    if not app_id:
        raise RuntimeError("Add HDX_EMAIL to backend/.env (your email; HDX uses it to identify the app)")
    ipc = ipc_latest(get_all("food-security", app_id, ipc_phase="3+"))
    # Only the last ~9 months are needed for a 3-month change (filter names differ between HAPI versions; unknown ones are ignored)
    since = (date.today() - timedelta(days=270)).isoformat()
    prices = price_changes(get_all("food-prices-market-monitor", app_id, start_date=since, reference_period_start_min=since))
    poverty = poverty_latest(get_all("poverty-rate", app_id))
    from app.services.sources.hapi_un import fetch_all
    problems: list[str] = []
    un = fetch_all(app_id, problems.append)
    status = sync(db, ipc, prices, poverty, source_id, un)
    return status + (f" (skipped: {'; '.join(problems)})" if problems else "")


KIND = SourceKind.hdx_hapi
