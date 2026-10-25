"""ReliefWeb (UN OCHA): situation reports, assessments and news about Pakistan, added to the report library.

Needs an approved appname (apidoc.reliefweb.int) in RELIEFWEB_APPNAME. Until then this source stays off and
the library is filled by uploads, links and the news scan.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.enums import SourceKind
from app.services.rag.ingest import IngestError, add_report
from app.services.rag.text import clean

URL = "https://api.reliefweb.int/v2/reports"
KIND = SourceKind.reliefweb


def enabled() -> bool:
    return bool(settings.RELIEFWEB_APPNAME)


def _date(v: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def parse(data: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for item in data.get("data") or []:
        f = item.get("fields") or {}
        body = clean(str(f.get("body") or ""))
        if len(body.split()) < 60:
            continue   # maps and infographics have no text to read
        sources = f.get("source") or []
        out.append({
            "id": str(item.get("id")),
            "title": str(f.get("title") or "ReliefWeb report"),
            "text": body,
            "url": f.get("url_alias") or f.get("url"),
            "publisher": ", ".join(s.get("shortname") or s.get("name", "") for s in sources if isinstance(s, dict))[:160] or "ReliefWeb",
            "published_at": _date((f.get("date") or {}).get("created")),
        })
    return out


def fetch(days: int = 14, limit: int = 60) -> list[dict[str, Any]]:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00+00:00")
    body = {
        "filter": {"operator": "AND", "conditions": [
            {"field": "primary_country.iso3", "value": "pak"},
            {"field": "date.created", "value": {"from": since}},
        ]},
        "fields": {"include": ["title", "body", "url", "url_alias", "date.created", "source.shortname", "source.name"]},
        "sort": ["date.created:desc"],
        "limit": limit,
    }
    res = httpx.post(URL, params={"appname": settings.RELIEFWEB_APPNAME}, json=body, timeout=60)
    if res.status_code in (401, 403):
        raise RuntimeError("ReliefWeb refused the appname. Check RELIEFWEB_APPNAME is the approved one.")
    res.raise_for_status()
    return parse(res.json())


def sync(db: Session, items: list[dict[str, Any]]) -> str:
    added = 0
    for it in items:
        try:
            _, created = add_report(db, kind=KIND, title=it["title"], pages=[(None, it["text"])], url=it["url"],
                                    publisher=it["publisher"], published_at=it["published_at"], external_id=it["id"])
            added += created
        except IngestError:
            db.rollback()
    return f"{len(items)} Pakistan reports, {added} new in the library"


def fetch_and_sync(db: Session, _source_id: int) -> str:
    if not enabled():
        raise RuntimeError("Add RELIEFWEB_APPNAME to backend/.env once ReliefWeb approves it")
    return sync(db, fetch())
