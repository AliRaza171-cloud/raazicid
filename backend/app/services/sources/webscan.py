"""AI web scan (OpenAI or Claude, see services/llm.py): the AI searches official sources and major Pakistani news for disasters in the last 72 hours.

New events become *unconfirmed* alerts with their source links; an admin checks and confirms them.
Each scan uses up to 5 web searches ($10 per 1,000 searches) plus tokens: a few cents per scan.
"""

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DisasterAlert, Location, Report
from app.models.enums import AlertSeverity, AlertStatus, AlertType, SourceKind
from app.services import llm
from app.services.claude import extract_json
from app.services.gazetteer import find_places, load_places

DOMAINS = ["ndma.gov.pk", "pmd.gov.pk", "reliefweb.int", "gdacs.org", "dawn.com", "tribune.com.pk",
           "thenews.com.pk", "geo.tv", "arynews.tv", "app.com.pk"]
FIGURE_KEYS = ("people_affected", "families_affected", "deaths", "injured", "houses_damaged")

PROMPT = """Today is {today}. Search for natural disasters and weather emergencies in Pakistan that started or got worse
in the last 72 hours: floods, heavy rain, earthquakes, heatwaves, cold waves, cyclones, droughts, landslides.
Prefer official sources (NDMA, PDMA, PMD) and major Pakistani news.

Reply with JSON only, no other text:
{{"events": [{{
  "type": "flood | earthquake | cyclone | drought | heatwave | cold_wave | heavy_rain | other",
  "title": "short title, e.g. Flash floods in Swat",
  "areas": ["district, city or province names in Pakistan"],
  "severity": "watch | moderate | severe",
  "summary": "2-3 plain sentences, only facts stated in the sources",
  "figures": {{"people_affected": 0, "families_affected": 0, "deaths": 0, "injured": 0, "houses_damaged": 0}},
  "started_at": "YYYY-MM-DD or null",
  "sources": [{{"url": "https://...", "title": "..."}}]
}}]}}

Rules: include a figure only if a source states that number; leave it out otherwise. Do not guess.
If nothing qualifies, reply {{"events": []}}."""


def scan() -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    today = datetime.now(timezone.utc).strftime("%d %B %Y")
    res = llm.complete(PROMPT.format(today=today), web={"max_uses": 5, "allowed_domains": DOMAINS}, max_tokens=3000, timeout=180)
    text, cites = res.text, res.citations
    return parse(text), cites


def parse(text: str) -> list[dict[str, Any]]:
    try:
        data = extract_json(text)
    except ValueError:
        return []
    out = []
    for e in data.get("events", []) if isinstance(data, dict) else []:
        if not isinstance(e, dict) or not e.get("title"):
            continue
        try:
            atype = AlertType(str(e.get("type", "other")).strip().lower())
        except ValueError:
            atype = AlertType.other
        try:
            sev = AlertSeverity(str(e.get("severity", "watch")).strip().lower())
        except ValueError:
            sev = AlertSeverity.watch
        figures = {k: int(v) for k, v in (e.get("figures") or {}).items()
                   if k in FIGURE_KEYS and isinstance(v, (int, float)) and v > 0}
        started: Optional[datetime] = None
        try:
            started = datetime.fromisoformat(str(e.get("started_at"))[:10]).replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            pass
        sources = [{"url": s["url"], "title": str(s.get("title") or s["url"])[:300]}
                   for s in e.get("sources") or [] if isinstance(s, dict) and str(s.get("url", "")).startswith("http")]
        out.append({"type": atype, "severity": sev, "title": str(e["title"])[:200], "summary": str(e.get("summary") or "")[:2000],
                    "areas": [str(a) for a in e.get("areas") or []], "figures": figures, "started_at": started, "sources": sources})
    return out


def sync(db: Session, events: list[dict[str, Any]], source_id: int) -> str:
    places = load_places(db)
    since = datetime.now(timezone.utc) - timedelta(days=5)
    created = merged = 0
    for e in events:
        locs = find_places(", ".join(e["areas"]) + " " + e["title"], places)
        loc_ids = {p.id for p in locs}
        # Same kind of event in the same place recently = the same alert (GDACS or an earlier scan)
        existing = None
        for a in db.scalars(select(DisasterAlert).where(DisasterAlert.type == e["type"], DisasterAlert.created_at >= since,
                                                        DisasterAlert.status != AlertStatus.dismissed)):
            if (loc_ids & {l.id for l in a.locations}) or a.title.strip().lower() == e["title"].strip().lower():
                existing = a
                break
        if existing is None:
            existing = DisasterAlert(type=e["type"], severity=e["severity"], status=AlertStatus.unconfirmed, title=e["title"],
                                     summary=e["summary"] or None, reported_figures=e["figures"], started_at=e["started_at"])
            existing.locations = [db.get(Location, i) for i in loc_ids]
            db.add(existing)
            created += 1
        else:
            figs = dict(existing.reported_figures or {})
            for k, v in e["figures"].items():
                figs[k] = max(v, figs.get(k, 0))
            existing.reported_figures = figs
            if not existing.summary and e["summary"]:
                existing.summary = e["summary"]
            merged += 1
        for s in e["sources"]:
            h = hashlib.sha256(f"url:{s['url']}".encode()).hexdigest()
            rep = db.scalar(select(Report).where(Report.content_hash == h))
            if rep is None:
                rep = Report(source_id=source_id, title=s["title"], url=s["url"], content_hash=h,
                             publisher=s["url"].split("/")[2].replace("www.", ""), published_at=e["started_at"])
                db.add(rep)
            if rep not in existing.reports:
                existing.reports.append(rep)
    db.commit()
    return f"{len(events)} events found, {created} new alerts, {merged} added to existing alerts"


KIND = SourceKind.web_search
