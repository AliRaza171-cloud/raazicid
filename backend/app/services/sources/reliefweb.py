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
# UN agencies working in Pakistan (ReliefWeb source short names): education, health, food, refugees, disasters
UN_AGENCIES = ["UNICEF", "WFP", "WHO", "UNHCR", "OCHA", "UNDP", "UNFPA", "IOM", "FAO", "UN-Habitat", "UNESCO", "UN Women",
               "ILO", "UNOPS", "UN RC Pakistan"]
FIELDS = ["title", "body", "url", "url_alias", "date.created", "source.shortname", "source.name"]


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


def _post(body: dict[str, Any], timeout: float = 60) -> list[dict[str, Any]]:
    res = httpx.post(URL, params={"appname": settings.RELIEFWEB_APPNAME}, json=body, timeout=timeout)
    if res.status_code in (401, 403):
        raise RuntimeError("ReliefWeb refused the appname. Check RELIEFWEB_APPNAME is the approved one.")
    res.raise_for_status()
    return parse(res.json())


def query_body(days: int, limit: int, un_only: bool, words: Optional[str] = None) -> dict[str, Any]:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00+00:00")
    conditions: list[dict[str, Any]] = [
        {"field": "primary_country.iso3", "value": "pak"},
        {"field": "date.created", "value": {"from": since}},
    ]
    if un_only:
        conditions.append({"field": "source.shortname", "value": UN_AGENCIES, "operator": "OR"})
    body: dict[str, Any] = {"filter": {"operator": "AND", "conditions": conditions}, "fields": {"include": FIELDS},
                            "sort": ["date.created:desc"], "limit": limit}
    if words:
        body["query"] = {"value": words, "fields": ["title", "body"], "operator": "OR"}
        body["sort"] = ["score:desc", "date.created:desc"]
    return body


def fetch(days: int = 14, limit: int = 60) -> list[dict[str, Any]]:
    """Recent Pakistan reports: UN agencies first, then a few from everyone else (NGOs, government, media)."""
    items = _post(query_body(days, limit, un_only=True))
    seen = {i["id"] for i in items}
    items += [i for i in _post(query_body(days, 20, un_only=False)) if i["id"] not in seen]
    return items


def search(words: str, limit: int = 5, days: int = 365) -> list[dict[str, Any]]:
    """Live lookup for the need finder: the most relevant Pakistan reports of the last year for these words."""
    return _post(query_body(days, limit, un_only=False, words=words), timeout=30)


def sync(db: Session, items: list[dict[str, Any]]) -> str:
    added = 0
    for it in items:
        try:
            _, created = add_report(db, kind=KIND, title=it["title"], pages=[(None, it["text"])], url=it["url"],
                                    publisher=it["publisher"], published_at=it["published_at"], external_id=it["id"])
            added += created
        except IngestError:
            db.rollback()
    un = sum(1 for it in items if any(a.lower() in it["publisher"].lower() for a in UN_AGENCIES))
    return f"{len(items)} Pakistan reports ({un} from UN agencies), {added} new in the library"


def fetch_and_sync(db: Session, _source_id: int) -> str:
    if not enabled():
        raise RuntimeError("Add RELIEFWEB_APPNAME to backend/.env once ReliefWeb approves it")
    return sync(db, fetch())
