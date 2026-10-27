"""NGO finder for places in need (data source "ngo_finder"): find NGOs where they are missing, most needed first.

A "gap" is a place with high or urgent need for an item and no NGO we know nearby that takes it (30 km from a city or
district, 10 km from an area). For each gap, highest need first, three sources are tried, free ones first:
  1. OpenStreetMap: NGO, charity and social-facility offices around the city (free, no key).
  2. OCHA 3W (who does what where, from HDX, already stored): organisations working in that district on a sector
     that serves the needed item (shelter -> blankets, WASH -> hygiene...). UN agencies and government bodies are left
     out: they do not take donated goods. Their office address is not in 3W, so they are saved "approximate".
  3. AI web search for NGOs in that city that take the needed item (uses AI credit; at most NGO_AI_SEARCHES_PER_RUN).
Runs every NGO_FINDER_EVERY_HOURS (default daily) and from the admin buttons on Needs by area.
Every NGO found this way still needs the admin's checks (phone, banned lists) before donations are sent.
"""

import re
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Category, Location, NeedIndicator, NeedLevel, Ngo
from app.models.enums import LocationLevel
from app.services import llm, ngo_finder, ngo_sources
from app.services.geo import distance_km, in_pakistan
from app.services.locations import ancestor_ids, descendant_ids, location_path
from app.services.ngos import search_place
from app.services.sources.hapi_un import sector_categories

GAP_KM = {LocationLevel.city: 30, LocationLevel.region: 30, LocationLevel.area: 10}
NOT_NGO = re.compile(r"\b(UN|UNICEF|UNHCR|UNDP|UNFPA|UNOPS|UN-?HABITAT|UN ?WOMEN|WFP|WHO|IOM|FAO|OCHA|ILO|UNESCO|"
                     r"united nations|world food programme|world health organi[sz]ation|government|department|ministry|"
                     r"authority|NDMA|PDMA|directorate|district administration|commissioner)\b", re.I)
MAX_CITIES = 8


# ---------- pure helpers (unit-tested) ----------

@dataclass
class NeedSpot:
    location_id: Any
    category_id: int
    slug: str
    level: int
    score: float
    lat: Optional[float]
    lng: Optional[float]
    radius_km: float
    inside: set   # place ids an NGO may be filed under to count (the place and everything under it)


@dataclass
class NgoSpot:
    lat: float
    lng: float
    location_id: Any
    categories: set   # empty = takes everything


def covered(spot: NeedSpot, ngos: list[NgoSpot]) -> bool:
    for n in ngos:
        if n.categories and spot.category_id not in n.categories:
            continue
        if n.location_id in spot.inside:
            return True
        if spot.lat is not None and distance_km(spot.lat, spot.lng, n.lat, n.lng) <= spot.radius_km:
            return True
    return False


def gaps_of(spots: list[NeedSpot], ngos: list[NgoSpot]) -> list[NeedSpot]:
    """Places in high or urgent need with no NGO nearby that takes the item, highest need first."""
    return sorted((s for s in spots if s.level >= 2 and not covered(s, ngos)), key=lambda s: -s.score)


def is_ngo_name(name: str) -> bool:
    """UN agencies and government bodies do not take donated goods from the public."""
    return bool(name.strip()) and not NOT_NGO.search(name)


def candidates_from_3w(sectors_by_org: dict[str, list[str]], names: dict[str, str], slug: str) -> list[tuple[str, list[str]]]:
    """(organisation name, its sectors) from one place's 3W that work on a sector serving `slug`."""
    out = []
    for org, sectors in sectors_by_org.items():
        if any(slug in sector_categories(s) for s in sectors):
            full = names.get(org) or org
            if is_ngo_name(full) and is_ngo_name(org):
                out.append((full, sectors))
    return out


# ---------- database ----------

def ensure_centre(db: Session, loc: Location) -> Optional[tuple[float, float]]:
    """A place's map centre; districts added from HDX have none, so look them up once on OpenStreetMap and keep it."""
    for loc_id in ancestor_ids(db, loc.id):
        l = db.get(Location, loc_id)
        if l is not None and l.lat is not None and l.level != LocationLevel.province:
            return l.lat, l.lng
    path = location_path(db, loc.id)
    try:
        time.sleep(1.1)
        res = httpx.get(ngo_finder.NOMINATIM, timeout=20, params={"q": f"{path[-1]}, {path[0]}, Pakistan", "format": "jsonv2",
                                                                  "limit": 1, "countrycodes": "pk"},
                        headers={"User-Agent": f"RAAZICID-FYP/1.0 ({settings.HDX_EMAIL or 'raazicid-fyp'})"})
        hits = res.json() if res.status_code == 200 else []
    except (httpx.HTTPError, ValueError):
        hits = []
    if hits and in_pakistan(float(hits[0]["lat"]), float(hits[0]["lon"])):
        loc.lat, loc.lng = float(hits[0]["lat"]), float(hits[0]["lon"])
        db.commit()
        return loc.lat, loc.lng
    return None


def find_gaps(db: Session, within: Optional[Any] = None) -> list[NeedSpot]:
    locs = {l.id: l for l in db.scalars(select(Location))}
    slugs = {c.id: c.slug for c in db.scalars(select(Category))}
    allowed = set(descendant_ids(db, within)) if within else None
    spots = []
    for nl in db.scalars(select(NeedLevel).where(NeedLevel.level >= 2)):
        loc = locs.get(nl.location_id)
        if loc is None or loc.level == LocationLevel.province or (allowed is not None and loc.id not in allowed):
            continue
        centre = next(((l.lat, l.lng) for l in (locs.get(i) for i in ancestor_ids(db, loc.id))
                       if l is not None and l.lat is not None and l.level != LocationLevel.province), (None, None))
        spots.append(NeedSpot(loc.id, nl.category_id, slugs.get(nl.category_id, ""), nl.level, nl.score, centre[0], centre[1],
                              GAP_KM.get(loc.level, 30), set(descendant_ids(db, loc.id))))
    ngos = [NgoSpot(n.lat, n.lng, n.location_id, {c.id for c in n.categories})
            for n in db.scalars(select(Ngo).where(Ngo.is_active.is_(True)))]
    return gaps_of(spots, ngos)


def _osm(db: Session, city: Location, centre: tuple[float, float]) -> int:
    """New NGOs from OpenStreetMap around the city; NGOs known only by city get their pin. Returns how many were added."""
    offices = ngo_sources.osm_offices(centre[0], centre[1], ngo_sources.radius_for(city.level))
    known = list(db.scalars(select(Ngo).where(Ngo.location_id.in_(descendant_ids(db, city.id)))))
    added = 0
    for o in offices:
        n = next((k for k in known if ngo_sources.same_org(k.name, o["name"])), None)
        if n is not None:
            if n.location_approx:
                n.lat, n.lng, n.location_approx = o["lat"], o["lng"], False
            continue
        n = Ngo(name=o["name"], location_id=city.id, address=o["address"] or f"{city.name} (see the map pin)", lat=o["lat"],
                lng=o["lng"], location_approx=False, phone=o["phone"], website=o["website"],
                about=f"{o['kind'].capitalize()} on OpenStreetMap", source_url=o["url"], found_by="openstreetmap",
                takes_cooked_food=False, is_active=True)
        db.add(n)
        known.append(n)
        added += 1
    db.commit()
    return added


def _from_3w(db: Session, location_id: Any, slug: str, city: Location, centre: tuple[float, float]) -> int:
    """Organisations OCHA 3W says work on this need (`slug`) in the place's district, saved under its city
    (approximate: 3W has no office addresses)."""
    places = [i for i in ancestor_ids(db, location_id)
              if (db.get(Location, i) or Location()).level != LocationLevel.province]
    rows = list(db.scalars(select(NeedIndicator).where(NeedIndicator.indicator == "orgs_present",
                                                       NeedIndicator.location_id.in_(places))))
    known = list(db.scalars(select(Ngo).where(Ngo.location_id.in_(descendant_ids(db, city.id)))))
    cats = {c.slug: c for c in db.scalars(select(Category))}
    added = 0
    for ind in rows:
        meta = ind.meta or {}
        by_org: dict[str, list[str]] = {}
        for sector, orgs in (meta.get("sectors") or {}).items():
            for o in orgs:
                by_org.setdefault(o, []).append(sector)
        district = location_path(db, ind.location_id)[-1]
        for name, sectors in candidates_from_3w(by_org, meta.get("names") or {}, slug):
            if any(ngo_sources.same_org(k.name, name) for k in known):
                continue
            slugs = sorted({s for sec in sectors for s in sector_categories(sec)})
            n = Ngo(name=name[:160], location_id=city.id, address=f"{city.name} (office address not known yet: search the web or call)",
                    lat=centre[0], lng=centre[1], location_approx=True,
                    about=f"OCHA 3W: works on {', '.join(sectors)} in {district}", found_by="ocha_3w",
                    takes_cooked_food=False, is_active=True)
            n.categories = [cats[s] for s in slugs if s in cats]
            db.add(n)
            known.append(n)
            added += 1
    db.commit()
    return added


def _takes_any(n: Ngo, category_ids: set) -> bool:
    return not n.categories or bool({c.id for c in n.categories} & category_ids)


def for_alerts(db: Session, alert_id: Optional[Any] = None, use_ai: bool = True) -> str:
    """NGOs for disasters: for each active alert (or the one given), in the city of each place it names, make sure we
    know NGOs that take the items the disaster needs now (relief.py): OpenStreetMap, OCHA 3W for those items in that
    district, then one web search if still none. So an earthquake in Khuzdar comes with NGOs in Khuzdar to drop at."""
    from datetime import datetime, timedelta, timezone

    from app.models import DisasterAlert
    from app.models.enums import AlertStatus
    from app.services.relief import recommend
    since = datetime.now(timezone.utc) - timedelta(days=30)
    stmt = select(DisasterAlert).where(DisasterAlert.status.in_([AlertStatus.confirmed, AlertStatus.unconfirmed]),
                                       DisasterAlert.created_at >= since)
    if alert_id:
        stmt = select(DisasterAlert).where(DisasterAlert.id == alert_id)
    cats = {c.slug: c.id for c in db.scalars(select(Category))}
    ai_left = settings.NGO_AI_SEARCHES_PER_RUN if (use_ai and llm.available()) else 0
    lines, done = [], set()
    alerts = [(a.id, a.title, a.type, a.severity, (a.started_at or a.created_at).date(), [l.id for l in a.locations])
              for a in db.scalars(stmt)]
    for _, title, kind, severity, started, loc_ids in alerts:
        advice, _ = recommend(kind, severity, datetime.now(timezone.utc).date(), started)
        now_slugs = [x.slug for x in advice if x.when == "now" and x.slug in cats]
        need_ids = {cats[x] for x in now_slugs}
        for loc_id in loc_ids:
            city = search_place(db, loc_id)
            if city is None or city.id in done:
                continue
            done.add(city.id)
            name = city.name
            centre = ensure_centre(db, city)
            if centre is None:
                lines.append(f"{name}: no map position")
                continue
            inside = set(descendant_ids(db, city.id))
            def known() -> int:
                return sum(1 for n in db.scalars(select(Ngo).where(Ngo.is_active.is_(True)))
                           if _takes_any(n, need_ids) and (n.location_id in inside or
                                                           distance_km(centre[0], centre[1], n.lat, n.lng) <= 30))
            before = known()
            added = _osm(db, city, centre)
            for slug in now_slugs:
                added += _from_3w(db, loc_id, slug, city, centre)
            searched = ""
            if known() == 0 and ai_left > 0 and now_slugs:
                ai_left -= 1
                try:
                    added += ngo_finder.find_and_save(db, city.id, cats[now_slugs[0]])["added"]
                    searched = ", web search done"
                except (llm.LLMError, ValueError) as e:
                    searched = f", web search failed ({str(e)[:60]})"
            lines.append(f"{title}: {known()} NGOs in {name} take what is needed now ({before} before, {added} added{searched})")
    return "; ".join(lines) if lines else "No active disaster alerts."


def for_place(db: Session, location_id: Any, category_id: int, use_ai: bool = True) -> str:
    """NGOs that take one item for one place, whatever its need level (the admin asked from Needs by area)."""
    cat = db.get(Category, category_id)
    city = search_place(db, location_id)
    if cat is None or city is None:
        return "Choose a place and an item"
    slug, item, name = cat.slug, cat.name.lower(), city.name
    centre = ensure_centre(db, city)
    if centre is None:
        return f"We have no map position for {name}"
    inside = set(descendant_ids(db, city.id))

    def known() -> int:
        return sum(1 for n in db.scalars(select(Ngo).where(Ngo.is_active.is_(True)))
                   if _takes_any(n, {category_id}) and (n.location_id in inside or
                                                        distance_km(centre[0], centre[1], n.lat, n.lng) <= 30))
    before = known()
    added = _osm(db, city, centre) + _from_3w(db, location_id, slug, city, centre)
    note = ""
    if known() == 0 and use_ai and llm.available():
        try:
            added += ngo_finder.find_and_save(db, city.id, category_id)["added"]
            note = " Web search done."
        except (llm.LLMError, ValueError) as e:
            note = f" Web search failed: {str(e)[:120]}"
    after = known()
    return (f"{name}: {after} NGOs we know take {item} or everything ({before} before, {added} added from "
            f"OpenStreetMap, OCHA 3W{' and the web' if 'done' in note else ''}).{note}"
            + ("" if after else " None yet: add one you know on the NGOs page."))


def run(db: Session, source_id: int, location_id: Optional[Any] = None, use_ai: bool = True,
        alert_id: Optional[Any] = None, category_id: Optional[int] = None) -> str:
    if alert_id:   # one disaster, right after it was confirmed or added
        return for_alerts(db, alert_id, use_ai)
    if location_id and category_id:   # one place and item, asked from Needs by area
        return for_place(db, location_id, category_id, use_ai)
    alerts_line = for_alerts(db, None, use_ai) if location_id is None else ""
    gaps_line = _gaps_run(db, location_id, use_ai)
    return f"Disasters: {alerts_line} Places in need: {gaps_line}" if alerts_line and alerts_line != "No active disaster alerts." \
        else gaps_line


def _gaps_run(db: Session, location_id: Optional[Any], use_ai: bool) -> str:
    gaps = find_gaps(db, location_id)
    if not gaps:
        return "No gaps: every place in high or urgent need has an NGO nearby that takes the item."
    cities: dict[Any, NeedSpot] = {}
    for g in gaps:   # highest need first, one entry per city
        city = search_place(db, g.location_id)
        if city is not None and city.id not in cities:
            cities[city.id] = g
    ai_left = settings.NGO_AI_SEARCHES_PER_RUN if (use_ai and llm.available()) else 0
    osm_added = w3_added = web_added = 0
    searched, notes = [], []
    for city_id, gap in list(cities.items())[:MAX_CITIES]:
        city = db.get(Location, city_id)
        name = city.name
        centre = ensure_centre(db, city)
        if centre is None:
            notes.append(f"{name}: no map position")
            continue
        osm_added += _osm(db, city, centre)
        w3_added += _from_3w(db, gap.location_id, gap.slug, city, centre)
        still = [g for g in find_gaps(db, city_id)]
        if still and ai_left > 0:
            ai_left -= 1
            try:
                r = ngo_finder.find_and_save(db, city_id, still[0].category_id)
                web_added += r["added"]
                searched.append(name)
            except (llm.LLMError, ValueError) as e:
                notes.append(f"{name}: web search failed ({str(e)[:80]})")
                ai_left = 0 if getattr(e, "out_of_credit", False) else ai_left
    left = find_gaps(db, location_id)
    left_places = []
    for g in left:
        p = location_path(db, g.location_id)[-1]
        if p not in left_places:
            left_places.append(p)
    parts = [f"Checked {min(len(cities), MAX_CITIES)} places in need",
             f"OpenStreetMap added {osm_added}", f"OCHA 3W added {w3_added}"]
    parts.append(f"web search added {web_added} ({', '.join(searched)})" if searched else
                 "no web search" + ("" if use_ai and llm.available() else " (AI not set up or turned off)"))
    status = "; ".join(parts) + "."
    if left_places:
        status += f" Still no NGO for the need in: {', '.join(left_places[:8])}{'…' if len(left_places) > 8 else ''}."
    if notes:
        status += " " + "; ".join(notes[:4]) + "."
    return status + " Call new NGOs and tick the checks before sending donations."
