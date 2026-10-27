"""Find NGOs in a city with a web search (OpenAI or Claude, whichever is set up), then save them.

RAAZICID does not hand out donations itself: riders drop them at an NGO, charity or welfare trust in the donor's
city. When we know no NGO there that takes the item, the admin presses "Search the web" and this module:
  1. asks the AI to search the web for NGOs with an office in that city that accept donated goods,
  2. reads back a JSON list (name, address, phone, website, what they take, a source link),
  3. finds each address on the map with OpenStreetMap Nominatim (free, no key, one request a second);
     an address it cannot place gets the city centre and is marked "approximate" (the first delivery's GPS fixes it),
  4. saves new NGOs and fills in missing details of ones we already have (an admin's edits are never overwritten).
Takes 1-3 minutes. No database transaction is held during the web search (Neon closes idle ones).
"""

import re
import time
from typing import Any, Optional

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Category, Location, Ngo
from app.services import llm, ngo_sources
from app.services.claude import extract_json
from app.services.geo import distance_km, in_pakistan
from app.services.locations import ancestor_ids, descendant_ids
from app.services.ngos import search_place

NOMINATIM = "https://nominatim.openstreetmap.org/search"
MAX_FROM_CITY_KM = 40      # a geocoded address further than this from the city centre is the wrong place
MAX_NGOS = 8

PROMPT = """Find NGOs, charities and welfare trusts that have an office or centre in {city}, {province}, Pakistan
and accept donated goods (in kind){for_what}.

Only include organisations that really exist and are active, with an office in or near {city}: local welfare trusts,
orphanages, shelters, community kitchens, and the {city} branches of national ones (for example Edhi, Saylani,
Alkhidmat, Chhipa, JDC) only if they really have a branch in {city}.
For each one give:
- the street address of its office in {city} (not a head office in another city),
- phone number and website, if you found them,
- which kinds of goods it takes, using only these words: {slugs},
- whether it takes cooked food,
- one short sentence about what it does,
- the web page where you found it.

Reply with JSON only, inside ```json fences:
{{"ngos": [{{"name": "...", "address": "...", "phone": "...", "website": "...", "accepts": ["food", "clothes"],
"cooked_food": false, "about": "...", "source_url": "https://..."}}]}}
At most {max_ngos}. Leave a field "" when you did not find it. Never guess a phone number or an address."""


# ---------- pure helpers (unit-tested) ----------

def name_key(name: str) -> str:
    """'Edhi Foundation (Hyderabad)' and 'EDHI FOUNDATION' -> 'edhi foundation': to spot the same NGO twice."""
    name = re.sub(r"\(.*?\)", " ", name.lower())
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", name).split())


def _text(v: Any, limit: int) -> Optional[str]:
    t = " ".join(str(v or "").split())
    return t[:limit] or None


def parse_ngos(answer: str, allowed: list[str]) -> list[dict[str, Any]]:
    """Clean NGO rows from the AI's JSON. Rows without a name, and repeats, are dropped."""
    try:
        data = extract_json(answer)
    except (ValueError, TypeError):
        return []
    rows = data.get("ngos") if isinstance(data, dict) else None
    out, seen = [], set()
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        name = _text(r.get("name"), 160)
        if not name or name_key(name) in seen:
            continue
        seen.add(name_key(name))
        accepts = [a for a in (r.get("accepts") or []) if isinstance(a, str) and a in allowed]
        url = _text(r.get("source_url"), 500)
        site = _text(r.get("website"), 300)
        if site and not site.startswith(("http://", "https://")):
            site = "https://" + site
        out.append({
            "name": name, "address": _text(r.get("address"), 500), "phone": _text(r.get("phone"), 40),
            "website": site, "accepts": list(dict.fromkeys(accepts)), "cooked_food": r.get("cooked_food") is True,
            "about": _text(r.get("about"), 300), "source_url": url if url and url.startswith("http") else None,
        })
    return out[:MAX_NGOS]


def close_enough(lat: float, lng: float, centre: Optional[tuple[float, float]]) -> bool:
    """A geocoded address is only trusted inside Pakistan and near the city."""
    if not in_pakistan(lat, lng):
        return False
    return centre is None or distance_km(lat, lng, centre[0], centre[1]) <= MAX_FROM_CITY_KM


# ---------- network ----------

def geocode(address: str, city: str, centre: Optional[tuple[float, float]]) -> Optional[tuple[float, float]]:
    """(lat, lng) of an address in a city from OpenStreetMap, or None. Waits a second (Nominatim's limit)."""
    contact = settings.HDX_EMAIL or "raazicid-fyp"
    for q in (f"{address}, {city}, Pakistan", f"{address}, Pakistan"):
        time.sleep(1.1)
        try:
            res = httpx.get(NOMINATIM, timeout=20, params={"q": q, "format": "jsonv2", "limit": 1, "countrycodes": "pk"},
                            headers={"User-Agent": f"RAAZICID-FYP/1.0 ({contact})"})
            hits = res.json() if res.status_code == 200 else []
        except (httpx.HTTPError, ValueError):
            return None
        if hits:
            lat, lng = float(hits[0]["lat"]), float(hits[0]["lon"])
            if close_enough(lat, lng, centre):
                return lat, lng
    return None


# ---------- the search ----------

def find_and_save(db: Session, location_id, category_id: Optional[int] = None) -> dict[str, Any]:
    """Search the web for NGOs in the city of `location_id` and save them. Raises llm.LLMError when the AI fails."""
    place = search_place(db, location_id)
    if place is None:
        raise ValueError("Choose a city or district")
    chain = [db.get(Location, i) for i in ancestor_ids(db, place.id)]
    with_coords = next((l for l in chain if l is not None and l.lat is not None), None)
    # plain values: nothing below may touch ORM objects while no transaction is open
    city_id, city, province = place.id, place.name, (chain[-1].name if chain and chain[-1] else "")
    centre = (with_coords.lat, with_coords.lng) if with_coords else None
    centre_is_city = with_coords is not None and with_coords.id == place.id
    cats = {c.slug: c.id for c in db.scalars(select(Category))}
    cat = db.get(Category, category_id) if category_id else None
    for_what = f", especially {cat.name.lower()}" if cat else ""
    db.commit()

    answer = llm.complete(PROMPT.format(city=city, province=province, for_what=for_what, slugs=", ".join(cats),
                                        max_ngos=MAX_NGOS),
                          web={"max_uses": 5}, max_tokens=3000, timeout=240)
    found = parse_ngos(answer.text, list(cats))
    offices: Optional[list[dict[str, Any]]] = None
    for f in found:
        spot = geocode(f["address"], city, centre if centre_is_city else None) if f["address"] else None
        if spot is None and centre is not None:   # no address on the map: is its office tagged on OpenStreetMap?
            if offices is None:
                offices = ngo_sources.osm_offices(centre[0], centre[1], 20000)
            hit = next((o for o in offices if ngo_sources.same_org(f["name"], o["name"])), None)
            if hit:
                spot = (hit["lat"], hit["lng"])
                f["address"] = f["address"] or hit["address"]
                f["phone"] = f["phone"] or hit["phone"]
        f["lat"], f["lng"], f["approx"] = (spot[0], spot[1], False) if spot else (*(centre or (30.38, 69.35)), True)

    inside = descendant_ids(db, city_id)
    known_list = list(db.scalars(select(Ngo).where(Ngo.location_id.in_(inside))))
    by_id = {c.id: c for c in db.scalars(select(Category))}
    added = updated = 0
    for f in found:
        n = next((k for k in known_list if name_key(k.name) == name_key(f["name"]) or ngo_sources.same_org(k.name, f["name"])), None)
        if n is None:
            n = Ngo(name=f["name"], location_id=city_id, address=f["address"] or f"{city} (address not found: call first)",
                    lat=f["lat"], lng=f["lng"], location_approx=f["approx"], phone=f["phone"], website=f["website"],
                    about=f["about"], takes_cooked_food=f["cooked_food"], source_url=f["source_url"], found_by="web_search",
                    is_active=True)
            n.categories = [by_id[cats[s]] for s in f["accepts"] if s in cats]
            db.add(n)
            known_list.append(n)
            added += 1
            continue
        changed = False
        for field in ("phone", "website", "about", "source_url"):   # fill blanks only: an admin's edits stay
            if not getattr(n, field) and f[field]:
                setattr(n, field, f[field])
                changed = True
        if n.location_approx and not f["approx"]:
            n.lat, n.lng, n.location_approx = f["lat"], f["lng"], False
            changed = True
        updated += changed
    db.commit()
    total = db.scalar(select(func.count()).select_from(Ngo).where(Ngo.location_id.in_(inside), Ngo.is_active.is_(True))) or 0
    status = (f"Found {len(found)} NGOs in {city} on the web: {added} new, {updated} updated. "
              f"{total} known in {city} now · {llm.used_label()}") if found else \
        f"The web search found no NGOs in {city} that take donated goods. Try again, or add one by hand."
    return {"place": city, "place_id": city_id, "found": len(found), "added": added, "updated": updated, "status": status}
