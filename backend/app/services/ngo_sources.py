"""More about NGOs from open data: who works where (OCHA 3W) and office locations (OpenStreetMap).

OCHA 3W ("who does what where", fetched daily through HDX HAPI and stored as "orgs_present" indicators) lists the
organisations working in each district by sector. An NGO we know is matched to those organisations by name, so its
page says "Works on WASH, Shelter in Dadu (OCHA 3W)", and during a disaster NGOs active in the disaster's districts
are shown first.

OpenStreetMap (Overpass API, free, no key) has offices tagged as NGOs, charities, foundations and social facilities.
They fill in a map location when the web search found no address, and can be added as NGOs to call.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Location, NeedIndicator
from app.models.enums import LocationLevel

OVERPASS = "https://overpass-api.de/api/interpreter"
STOP = {"the", "of", "for", "and", "pakistan", "pak", "foundation", "trust", "welfare", "organisation", "organization",
        "society", "international", "association", "ngo", "charity", "charitable", "network", "program", "programme",
        "development", "center", "centre", "pvt", "ltd", "limited", "registered", "intl", "org"}


# ---------- matching names (pure, unit-tested) ----------

def words(name: str) -> list[str]:
    name = re.sub(r"\(.*?\)", " ", (name or "").lower())
    return re.sub(r"[^a-z0-9 ]+", " ", name).split()


def core(name: str) -> set[str]:
    """The distinctive words of a name: 'Edhi Welfare Organization' -> {'edhi'}."""
    return {w for w in words(name) if w not in STOP and len(w) > 1}


def initials(name: str) -> str:
    return "".join(w[0] for w in words(name) if w not in {"the", "of", "for", "and"}).upper()


def same_org(a: str, b: str) -> bool:
    """True when two names very likely mean the same organisation ('Edhi Foundation' / 'EDHI Welfare Organization',
    'Alkhidmat Foundation Pakistan' / 'AKFP' is not guessed, but 'Norwegian Refugee Council' / 'NRC' is)."""
    ca, cb = core(a), core(b)
    if not ca or not cb:
        return False
    if ca == cb:
        return True
    small, big = (ca, cb) if len(ca) <= len(cb) else (cb, ca)
    if len(small) >= 2 and small <= big:
        return True
    for x, y in ((a, b), (b, a)):   # an acronym on one side
        short = re.sub(r"[^A-Za-z]", "", x)
        if 3 <= len(short) <= 6 and short.isupper() and len(words(x)) == 1 and short == initials(y):
            return True
    return False


@dataclass
class Presence:
    location_id: Any
    place: str
    level: str
    sectors: list[str]
    org: str
    period_end: Optional[date] = None


@dataclass
class Works:
    """Where one NGO works according to 3W: place -> sectors."""
    places: dict[str, list[str]] = field(default_factory=dict)
    location_ids: set = field(default_factory=set)
    period_end: Optional[date] = None

    def text(self, limit: int = 3) -> Optional[str]:
        if not self.places:
            return None
        sectors = sorted({s for v in self.places.values() for s in v})
        names = list(self.places)
        where = ", ".join(names[:limit]) + (f" and {len(names) - limit} more" if len(names) > limit else "")
        when = f", {self.period_end:%b %Y}" if self.period_end else ""
        return f"Works on {', '.join(sectors[:4])} in {where} (OCHA 3W{when})"


def works_for(name: str, index: list[Presence]) -> Works:
    w = Works()
    for p in index:
        if same_org(name, p.org):
            for s in p.sectors:
                if s not in w.places.setdefault(p.place, []):
                    w.places[p.place].append(s)
            w.location_ids.add(p.location_id)
            if p.period_end and (w.period_end is None or p.period_end > w.period_end):
                w.period_end = p.period_end
    return w


def load_index(db: Session) -> list[Presence]:
    """Every (place, organisation, sectors) from the stored 3W. One query; use for a whole list of NGOs."""
    names = {l.id: (l.name, l.level.value) for l in db.scalars(select(Location))}
    out = []
    for ind in db.scalars(select(NeedIndicator).where(NeedIndicator.indicator == "orgs_present")):
        meta = ind.meta or {}
        place, level = names.get(ind.location_id, ("?", ""))
        full = meta.get("names") or {}
        by_org: dict[str, list[str]] = {}
        for sector, orgs in (meta.get("sectors") or {}).items():
            for o in orgs:
                by_org.setdefault(o, []).append(sector)
        for o, sectors in by_org.items():
            out.append(Presence(ind.location_id, place, level, sectors, o, ind.period_end))
            if full.get(o) and full[o] != o:
                out.append(Presence(ind.location_id, place, level, sectors, full[o], ind.period_end))
    return out


# ---------- OpenStreetMap (pure parser, unit-tested) ----------

# Pakistan's big charity networks that take donated goods. On the map their centres are often tagged as an ambulance
# station, a clinic or a shop, not as an NGO office, so they are also looked for by name (English and Urdu).
NETWORKS = ["Edhi", "Saylani", "Sailani", "JDC", "Al-?Khidmat", "Chhipa", "Chippa", "Akhuwat", "Rizq", "Robin Hood Army",
            "ایدھی", "سیلانی", "الخدمت", "چھیپا", "اخوت"]


def overpass_query(lat: float, lng: float, radius_m: int) -> str:
    around = f"(around:{radius_m},{lat},{lng})"
    names = "|".join(NETWORKS)
    return (f'[out:json][timeout:25];('
            f'nwr["office"~"^(ngo|charity|foundation|association|non_profit)$"]{around};'
            f'nwr["amenity"="social_facility"]{around};'
            f'nwr["social_facility"]{around};'
            f'nwr["name"~"{names}",i]{around};'
            f'nwr["name:en"~"{names}",i]{around};'
            f');out center tags 200;')


def parse_osm(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Named offices with a location, address, phone and website when tagged. Repeats (same name) are dropped."""
    out, seen = [], set()
    for e in data.get("elements") or []:
        tags = e.get("tags") or {}
        name = (tags.get("name:en") or tags.get("name") or "").strip()
        lat = e.get("lat", (e.get("center") or {}).get("lat"))
        lng = e.get("lon", (e.get("center") or {}).get("lon"))
        if not name or lat is None or lng is None:
            continue
        key = " ".join(words(name))
        if key in seen:
            continue
        seen.add(key)
        street = " ".join(x for x in (tags.get("addr:housenumber"), tags.get("addr:street")) if x)
        address = tags.get("addr:full") or ", ".join(x for x in (street, tags.get("addr:suburb"), tags.get("addr:city")) if x)
        kind = tags.get("office") or tags.get("social_facility") or tags.get("amenity") or "office"
        out.append({"name": name[:160], "lat": float(lat), "lng": float(lng), "address": address[:300] or None,
                    "phone": (tags.get("phone") or tags.get("contact:phone") or "")[:40] or None,
                    "website": tags.get("website") or tags.get("contact:website") or None,
                    "kind": kind.replace("_", " "),
                    "url": f"https://www.openstreetmap.org/{e.get('type', 'node')}/{e.get('id')}"})
    return out


def osm_offices(lat: float, lng: float, radius_m: int = 15000) -> list[dict[str, Any]]:
    """NGO and charity offices near a point, from OpenStreetMap. Empty list if Overpass is busy or unreachable."""
    contact = settings.HDX_EMAIL or "raazicid-fyp"
    try:
        res = httpx.post(OVERPASS, data={"data": overpass_query(lat, lng, radius_m)}, timeout=40,
                         headers={"User-Agent": f"RAAZICID-FYP/1.0 ({contact})"})
        return parse_osm(res.json()) if res.status_code == 200 else []
    except (httpx.HTTPError, ValueError):
        return []


def radius_for(level: LocationLevel) -> int:
    return {LocationLevel.city: 15000, LocationLevel.region: 12000, LocationLevel.area: 5000}.get(level, 20000)
