"""GDACS (Global Disaster Alert and Coordination System): floods, earthquakes, cyclones and droughts.

No key needed. The event list has no country filter, so we ask for the last days worldwide and keep Pakistan.
Each event becomes an *unconfirmed* alert on the nearest city or province; an admin confirms it.
"""

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DisasterAlert, Location, Report
from app.models.enums import AlertSeverity, AlertStatus, AlertType, SourceKind
from app.services.gazetteer import find_places, load_places, nearest_place

URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
TYPES = {"EQ": AlertType.earthquake, "FL": AlertType.flood, "TC": AlertType.cyclone, "DR": AlertType.drought}
SEVERITY = {"green": AlertSeverity.watch, "orange": AlertSeverity.moderate, "red": AlertSeverity.severe}
RANK = {AlertSeverity.watch: 0, AlertSeverity.moderate: 1, AlertSeverity.severe: 2}


def is_pakistan(p: dict[str, Any]) -> bool:
    if str(p.get("iso3", "")).upper() == "PAK" or "pakistan" in str(p.get("country", "")).lower():
        return True
    return any(isinstance(c, dict) and str(c.get("iso3", "")).upper() == "PAK" for c in p.get("affectedcountries") or [])


def _date(v: Any) -> Optional[datetime]:
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def parse(geojson: dict[str, Any]) -> list[dict[str, Any]]:
    """Pakistan events from a GDACS event list, in a simple shape."""
    out = []
    for f in geojson.get("features") or []:
        p = f.get("properties") or {}
        if not is_pakistan(p) or p.get("eventtype") not in TYPES:
            continue
        coords = (f.get("geometry") or {}).get("coordinates")
        lat = lng = None
        if isinstance(coords, list) and len(coords) >= 2 and all(isinstance(c, (int, float)) for c in coords[:2]):
            lng, lat = float(coords[0]), float(coords[1])
        url = p.get("url")
        out.append({
            "key": f"{p.get('eventtype')}{p.get('eventid')}",
            "type": TYPES[p["eventtype"]],
            "severity": SEVERITY.get(str(p.get("alertlevel", "")).lower(), AlertSeverity.watch),
            "name": p.get("name") or p.get("eventname") or "",
            "description": p.get("description") or "",
            "started_at": _date(p.get("fromdate")),
            "lat": lat, "lng": lng,
            "url": url.get("report") if isinstance(url, dict) else (url if isinstance(url, str) else None),
        })
    return out


def fetch(days: int = 14) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    params = {"eventlist": "EQ;TC;FL;DR", "alertlevel": "Green;Orange;Red", "pageSize": 100,
              "fromDate": (now - timedelta(days=days)).strftime("%Y-%m-%d"), "toDate": now.strftime("%Y-%m-%d")}
    events, page = [], 1
    while page <= 10:
        res = httpx.get(URL, params={**params, "pageNumber": page}, timeout=60)
        if res.status_code == 204:
            break
        res.raise_for_status()
        data = res.json()
        events += parse(data)
        if len(data.get("features") or []) < 100:
            break
        page += 1
    return events


def sync(db: Session, events: list[dict[str, Any]], source_id: int) -> str:
    """Create or update alerts. Returns a short status line."""
    places = load_places(db)
    created = updated = 0
    for e in events:
        alert = db.scalar(select(DisasterAlert).where(DisasterAlert.gdacs_event_id == e["key"]))
        if alert is None:
            locs = find_places(f"{e['name']} {e['description']}", places)
            if not locs and e["lat"] is not None:
                near, km = nearest_place(e["lat"], e["lng"], places)
                if near is not None:
                    locs = [near]
            title = e["name"] or f"{e['type'].value.replace('_', ' ').title()} in Pakistan"
            alert = DisasterAlert(type=e["type"], severity=e["severity"], status=AlertStatus.unconfirmed, title=title[:200],
                                  summary=(e["description"] or None), gdacs_event_id=e["key"], started_at=e["started_at"],
                                  reported_figures={})
            alert.locations = [db.get(Location, p.id) for p in locs]
            db.add(alert)
            created += 1
        else:
            if RANK[e["severity"]] > RANK[alert.severity]:
                alert.severity = e["severity"]
                updated += 1
        if e["url"]:
            h = hashlib.sha256(f"gdacs:{e['key']}".encode()).hexdigest()
            rep = db.scalar(select(Report).where(Report.content_hash == h))
            if rep is None:
                rep = Report(source_id=source_id, external_id=e["key"], title=alert.title, url=e["url"], publisher="GDACS",
                             published_at=e["started_at"], content_hash=h)
                db.add(rep)
            if rep not in alert.reports:
                alert.reports.append(rep)
    db.commit()
    return f"{len(events)} Pakistan events, {created} new alerts, {updated} updated"


KIND = SourceKind.gdacs
