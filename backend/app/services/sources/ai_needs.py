"""AI web scan for current needs: the AI (OpenAI or Claude) searches news, UN and NGO reports from the last 90 days
and lists where people need which items, with source links.

UN datasets (IPC, poverty, people in need) are published every year or two, so on their own they make "Needs by
area" look out of date. This scan adds fresh, linked evidence. One scan per province or for all of Pakistan; an
admin starts it (or set AI_NEEDS_EVERY_DAYS). Each scan replaces the previous one for the same province.
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Category, Location, NeedIndicator
from app.services import llm
from app.services.claude import extract_json
from app.services.gazetteer import find_places, load_places
from app.services.locations import descendant_ids

SLUGS = ["food", "grocery_ration", "clothes", "blankets", "winter_support", "hygiene", "baby", "household",
         "school_supplies", "books", "mobility_aids", "emergency_relief"]
LEVELS = {"urgent": 3, "high": 2, "some": 1}
MAX_AGE_DAYS = 120   # a little more than the 90 asked for: reports are often dated a few days late

PROMPT = """Today is {today}. Search the web for reports from the last 90 days about what people need in {scope}.
Prefer UN agencies (UNICEF, WFP, WHO, UNHCR, OCHA, UNDP, IOM, FAO), NDMA / PDMA, NGOs and major Pakistani news.

RAAZICID is a charity that collects and hands out goods. Only these needs count:
food (cooked meals), grocery_ration (flour, rice, oil), clothes, blankets, winter_support (warm clothes, heaters),
hygiene (soap, sanitary items, hygiene kits), baby (milk, nappies), household (utensils, mattresses, tents),
school_supplies, books, mobility_aids (wheelchairs), emergency_relief (after floods, earthquakes, displacement).

Reply with JSON only, inside ```json fences:
{{"needs": [{{
  "area": "district or city in Pakistan",
  "province": "province",
  "categories": ["hygiene", "baby"],
  "level": "urgent | high | some",
  "why": "one plain sentence with the numbers the source gives",
  "date": "YYYY-MM-DD (date of the source)",
  "sources": [{{"url": "https://...", "title": "..."}}]
}}]}}
Rules: only needs stated in sources from the last 90 days; name a district or city whenever the source does; never guess
numbers or places; at most 15 items, most serious first. If nothing qualifies, reply {{"needs": []}}."""


def parse(text: str, today: Optional[date] = None) -> list[dict[str, Any]]:
    """Clean items from the AI's JSON: known categories only, recent dates only, real links only."""
    today = today or datetime.now(timezone.utc).date()
    try:
        data = extract_json(text)
    except ValueError:
        return []
    out = []
    for n in (data.get("needs") or []) if isinstance(data, dict) else []:
        if not isinstance(n, dict) or not str(n.get("area") or "").strip():
            continue
        cats = [c for c in dict.fromkeys(str(c).strip().lower() for c in n.get("categories") or []) if c in SLUGS]
        if not cats:
            continue
        try:
            when = date.fromisoformat(str(n.get("date"))[:10])
        except ValueError:
            when = today
        if when > today:
            when = today
        if (today - when).days > MAX_AGE_DAYS:
            continue   # old news: the UN datasets already cover the past
        sources = [{"url": s["url"], "title": str(s.get("title") or s["url"])[:200]}
                   for s in n.get("sources") or [] if isinstance(s, dict) and str(s.get("url", "")).startswith("http")][:3]
        out.append({"area": str(n["area"]).strip()[:120], "province": str(n.get("province") or "").strip()[:60], "categories": cats,
                    "level": LEVELS.get(str(n.get("level") or "").strip().lower(), 1), "why": str(n.get("why") or "")[:400],
                    "date": when, "sources": sources})
    return out[:15]


def scan(scope: str) -> list[dict[str, Any]]:
    """Ask the AI (with web search). Slow: up to a few minutes."""
    today = datetime.now(timezone.utc)
    res = llm.complete(PROMPT.format(today=today.strftime("%d %B %Y"), scope=scope),
                       web={"max_uses": 6, "allowed_domains": None}, max_tokens=3000, timeout=240)
    items = parse(res.text, today.date())
    if res.citations:   # items without their own links get the pages the AI quoted
        for it in items:
            if not it["sources"]:
                it["sources"] = [{"url": c["url"], "title": c["title"]} for c in res.citations[:2]]
    return items


def sync(db: Session, items: list[dict[str, Any]], source_id: int, province_id: Optional[uuid.UUID] = None) -> str:
    """Replace this scope's previous scan with the new items."""
    stmt = delete(NeedIndicator).where(NeedIndicator.source_id == source_id, NeedIndicator.indicator == "ai_need")
    if province_id:
        stmt = stmt.where(NeedIndicator.location_id.in_(descendant_ids(db, province_id)))
    db.execute(stmt)
    places = load_places(db)
    inside = set(descendant_ids(db, province_id)) if province_id else None
    cat_ids = {c.slug: c.id for c in db.scalars(select(Category))}
    added, skipped = 0, 0
    for it in items:
        found = find_places(f"{it['area']}, {it['province']}", places) or find_places(it["province"], places)
        loc = found[0] if found else None
        if loc is None or (inside is not None and loc.id not in inside):
            skipped += 1
            continue
        for slug in it["categories"]:
            db.add(NeedIndicator(location_id=loc.id, category_id=cat_ids.get(slug), indicator="ai_need", value=it["level"],
                                 period_start=it["date"], period_end=it["date"], source_id=source_id,
                                 meta={"why": it["why"], "sources": it["sources"], "area": it["area"], "model": llm.label()}))
        added += 1
    db.commit()
    where = "" if not skipped else f" ({skipped} not matched to our places)"
    return f"{len(items)} needs found, {added} added{where} · {llm.label()}"


def run(db: Session, source_id: int, province_id: Optional[uuid.UUID] = None) -> str:
    """Scan one province (or all Pakistan) without holding a database transaction during the AI call."""
    scope = f"{db.get(Location, province_id).name} province, Pakistan" if province_id else "Pakistan (all provinces)"
    db.commit()
    items = scan(scope)
    return sync(db, items, source_id, province_id)


def run_all(db: Session, source_id: int) -> str:
    """For the scheduler and "Run now": the whole country in one scan."""
    return run(db, source_id, None)


def stale_before() -> date:
    return datetime.now(timezone.utc).date() - timedelta(days=MAX_AGE_DAYS)
