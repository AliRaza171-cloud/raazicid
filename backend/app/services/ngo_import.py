"""Import a list of NGOs the admin has collected (CSV or Excel): one row per NGO, with the districts it works in.

Columns are found by their heading, in any order and any case:
  name      NGO name (required)
  district  one or more districts or cities, separated by ";" (required): "Dadu; Badin; Jamshoro"
  province  optional; lets districts we do not have yet be added under it
  address, phone, website, email, about, takes ("Food; Grocery / ration"; empty = not confirmed), lat, lng

Each NGO is saved once per district it works in, so it shows under that place on Needs by area. Without a map
position or an office address the district centre is used and marked "address not known yet" (call them). An NGO
already saved in that district (same name) gets the missing details filled in instead of a copy.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, Location, Ngo
from app.services.geo import in_pakistan
from app.services.ngo_sources import core

HEADINGS = {
    "name": ("name", "ngo", "organisation", "organization", "ngo name"),
    "district": ("district", "districts", "city", "cities", "place", "places", "where", "works in", "areas"),
    "province": ("province",),
    "address": ("address", "office", "office address"),
    "phone": ("phone", "phone number", "contact", "mobile", "tel", "telephone"),
    "website": ("website", "web", "url", "site", "link"),
    "email": ("email", "e-mail"),
    "about": ("about", "notes", "note", "description", "work", "why", "why they are relevant"),
    "takes": ("takes", "items", "accepts", "categories", "takes items"),
    "lat": ("lat", "latitude"),
    "lng": ("lng", "lon", "long", "longitude"),
}
SPLIT = re.compile(r"\s*[;|\n]\s*")


@dataclass
class Row:
    name: str
    districts: list[str]
    province: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    email: Optional[str] = None
    about: Optional[str] = None
    takes: list[str] = field(default_factory=list)
    lat: Optional[float] = None
    lng: Optional[float] = None


# ---------- reading (pure, unit-tested) ----------

def _text(v: Any) -> Optional[str]:
    t = re.sub(r"\s+", " ", str(v if v is not None else "")).strip()
    return t or None


def _num(v: Any) -> Optional[float]:
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def find_columns(head: list[Any]) -> dict[str, int]:
    names = [(_text(h) or "").lower().rstrip(":") for h in head]
    cols: dict[str, int] = {}
    for key, words in HEADINGS.items():
        for i, h in enumerate(names):
            if i not in cols.values() and h in words:
                cols[key] = i
                break
    return cols


def parse_rows(rows: list[list[Any]]) -> tuple[list[Row], list[str]]:
    """NGO rows from a table; the heading row is the first one with a name and a district column."""
    problems: list[str] = []
    start = next((i for i, r in enumerate(rows[:10]) if {"name", "district"} <= set(find_columns(r))), None)
    if start is None:
        return [], ["No heading row with a 'name' and a 'district' column"]
    cols = find_columns(rows[start])
    out = []
    for n, r in enumerate(rows[start + 1:], start=start + 2):
        def get(key: str) -> Any:
            i = cols.get(key)
            return r[i] if i is not None and i < len(r) else None
        name = _text(get("name"))
        places = [p for p in SPLIT.split(_text(get("district")) or "") if p]
        if not name and not places:
            continue
        if not name or not places:
            problems.append(f"Row {n}: needs both a name and a district")
            continue
        lat, lng = _num(get("lat")), _num(get("lng"))
        if lat is not None and (lng is None or not in_pakistan(lat, lng)):
            problems.append(f"Row {n} ({name}): map position not in Pakistan, district centre used")
            lat = lng = None
        out.append(Row(name=name[:160], districts=places, province=_text(get("province")), address=_text(get("address")),
                       phone=(_text(get("phone")) or "")[:40] or None, website=_text(get("website")), email=_text(get("email")),
                       about=_text(get("about")), takes=[t for t in SPLIT.split(_text(get("takes")) or "") if t],
                       lat=lat, lng=lng))
    return out, problems


def category_ids(names: list[str], cats: dict[str, int]) -> tuple[list[int], list[str]]:
    """Our categories for the item names in a row ('grocery', 'Grocery / ration' -> 2). Unknown names are returned."""
    ids, unknown = [], []
    for name in names:
        key = re.sub(r"[^a-z]", "", name.lower())
        hit = next((cid for cname, cid in cats.items() if re.sub(r"[^a-z]", "", cname.lower()).startswith(key[:5]) and key), None)
        if hit is None:
            unknown.append(name)
        elif hit not in ids:
            ids.append(hit)
    return ids, unknown


def same_ngo(a: str, b: str) -> bool:
    """In one district: 'Saylani Welfare International Trust' is the 'Saylani Welfare Trust - Numaish Branch' we have."""
    ca, cb = core(a), core(b)
    return bool(ca and cb) and (ca <= cb or cb <= ca)


# ---------- saving ----------

def save(db: Session, rows: list[Row]) -> dict[str, Any]:
    from app.services.deprivation import clean_name, match
    from app.services.gazetteer import load_places
    from app.services.sources.hdx import _district, _province
    from app.services.sources.ngo_gaps import ensure_centre

    places = load_places(db)
    cats = {c.name: c.id for c in db.scalars(select(Category))}
    by_id = {c.id: c for c in db.scalars(select(Category))}
    added, updated, problems = 0, 0, []
    for row in rows:
        ids, unknown = category_ids(row.takes, cats)
        if unknown:
            problems.append(f"{row.name}: items not known ({', '.join(unknown)}), left out")
        about = "; ".join(x for x in (row.about, f"Email: {row.email}" if row.email else None) if x) or None
        for d in row.districts:
            prov = _province(row.province, places) if row.province else None
            p = match(d, places, prov) or (match(d, places) if prov is not None else None)
            loc = db.get(Location, p.id) if p else (_district(db, prov, clean_name(d), None, places) if prov else None)
            if loc is None:
                problems.append(f"{row.name}: place '{d}' not found (add a province column to add it)")
                continue
            exact = row.lat is not None and len(row.districts) == 1
            centre = (row.lat, row.lng) if exact else ensure_centre(db, loc)
            if centre is None:
                problems.append(f"{row.name}: no map position for {loc.name}")
                continue
            n = next((k for k in db.scalars(select(Ngo).where(Ngo.location_id == loc.id)) if same_ngo(k.name, row.name)), None)
            if n is None:
                n = Ngo(name=row.name, location_id=loc.id, lat=centre[0], lng=centre[1], location_approx=not exact,
                        address=(row.address if exact or len(row.districts) == 1 else None)
                        or f"{loc.name} (office address not known yet: call them)",
                        found_by="import", takes_cooked_food=False, is_active=True)
                n.categories = []
                db.add(n)
                added += 1
            else:
                updated += 1
            n.phone = n.phone or row.phone
            n.website = n.website or row.website
            n.source_url = n.source_url or row.website
            n.about = n.about or about
            have = {c.id for c in n.categories}
            n.categories = list(n.categories) + [by_id[i] for i in ids if i not in have]
            db.flush()
        db.commit()
    return {"ngos": len(rows), "added": added, "updated": updated, "problems": problems[:30]}
