"""AI web scan for current needs: the AI (OpenAI or Claude) searches news, UN and NGO reports from the last 90 days
and lists where people need which items, with source links.

UN datasets (IPC, poverty, people in need) are published every year or two, so on their own they make "Needs by
area" look out of date. This scan adds fresh, linked evidence. One scan per province or for all of Pakistan; an
admin starts it (or set AI_NEEDS_EVERY_DAYS). Each scan replaces the previous one for the same province.
"""

import re
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

CATEGORY_TEXT = {
    "food": "food (cooked meals)", "grocery_ration": "grocery_ration (flour, rice, oil)", "clothes": "clothes",
    "blankets": "blankets", "winter_support": "winter_support (warm clothes, heaters)",
    "hygiene": "hygiene (soap, sanitary items, hygiene kits)", "baby": "baby (milk, nappies)",
    "household": "household (utensils, mattresses, tents)", "school_supplies": "school_supplies", "books": "books",
    "mobility_aids": "mobility_aids (wheelchairs)", "emergency_relief": "emergency_relief (after floods, earthquakes, displacement)",
}
# Three searches per scan, one per theme, so one big report cannot fill the whole answer
THEMES = [
    ("food, hunger and rations", ["food", "grocery_ration", "baby"],
     "WFP, FAO, IPC, UNICEF nutrition, food prices, drought, malnutrition"),
    ("shelter, winter and disaster relief", ["blankets", "winter_support", "clothes", "household", "emergency_relief"],
     "NDMA / PDMA, OCHA, IOM, UNHCR, floods, cold waves, displaced and refugee families"),
    ("health, hygiene and education", ["hygiene", "baby", "school_supplies", "books", "mobility_aids"],
     "UNICEF, WHO, UNFPA, UNESCO, out-of-school children, textbooks, sanitation, disability"),
]
PER_SOURCE = 2   # at most this many findings from any one page
# NDMA's sitrep site is mostly tables of relief already handed out: not evidence that people still need it
BLOCKED = ["sitreps.ndma.gov.pk"]
REACHED = {"none": "no aid has reached them yet", "partial": "some aid has reached them, not enough", "unknown": ""}

# A finding must show a gap: words that say people still lack something. Aid handed out, on its own, is not a need.
GAP = re.compile(r"\b(unmet|gaps?|shortages?|short of|lack\w*|still (need|wait|without|in need|lack)\w*|waiting|"
                 r"not (yet )?(received|reached|been reached)|no (aid|assistance|help|relief|support)|unreached|hard[- ]to[- ]reach|"
                 r"without \w+|ran out|out of stock|insufficient|inadequate|"
                 r"needs?|needed|needing|require[sd]?|requirements?|demand|left out|neglected|inaccessible|cut off)\b", re.I)


def shows_gap(*texts: str) -> bool:
    """True when the text says people still lack something. Aid handed out, on its own, is not a need."""
    joined = " ".join(t for t in texts if t)
    return bool(GAP.search(joined))

PROMPT = """Today is {today}. Search the web for reports from the last 90 days about {theme} needs in {scope}.
Good places to look: {hint}, NGOs and major Pakistani news. Use several different sources.

RAAZICID is a charity that collects and hands out goods. Only these needs count here:
{categories}.

Reply with JSON only, inside ```json fences:
{{"needs": [{{
  "area": "district or city in Pakistan",
  "province": "province",
  "categories": ["{example}"],
  "level": "urgent | high | some",
  "why": "one plain sentence: who still lacks what, with the numbers the source gives",
  "unmet": "a short quote from the source that shows the gap, e.g. 'families are still waiting for blankets'",
  "reached": "none | partial | unknown  (has any aid reached these people yet?)",
  "date": "YYYY-MM-DD (date of the source)",
  "sources": [{{"url": "https://...", "title": "..."}}]
}}]}}
We look for UNMET needs: people who still lack something and whom nobody, or too few, have helped yet.
Search for words like "unmet needs", "still waiting", "not yet received", "no assistance", "hard to reach",
"gaps", "shortage", "ran out".
Rules:
- Only unmet needs stated in sources from the last 90 days. Never guess numbers or places.
- Aid that was distributed, provided or delivered is NOT a need. Leave it out unless the same source says people
  still lack it, stocks ran out or more is needed; then "unmet" must quote that sentence.
- Every item needs an "unmet" quote. No quote, no item.
- At most {per_source} items from the same source; use different sources for different areas.
- "urgent": many people lack it now and no aid has reached them. "high": a clear, large gap. "some": a smaller or partial gap.
- Name a district or city whenever the source does. At most 8 items, most serious first.
If nothing qualifies, reply {{"needs": []}}."""


def parse(text: str, today: Optional[date] = None, allowed: Optional[list[str]] = None,
          max_age_days: int = MAX_AGE_DAYS, default_date: Optional[date] = None) -> list[dict[str, Any]]:
    """Clean items from the AI's JSON: known categories only, recent dates only, real links only, a gap shown."""
    today = today or datetime.now(timezone.utc).date()
    allowed = allowed or SLUGS
    try:
        data = extract_json(text)
    except ValueError:
        return []
    out = []
    for n in (data.get("needs") or []) if isinstance(data, dict) else []:
        if not isinstance(n, dict) or not str(n.get("area") or "").strip():
            continue
        cats = [c for c in dict.fromkeys(str(c).strip().lower() for c in n.get("categories") or []) if c in allowed]
        if not cats:
            continue
        try:
            when = date.fromisoformat(str(n.get("date"))[:10])
        except ValueError:
            when = default_date or today
        if when > today:
            when = today
        if (today - when).days > max_age_days:
            continue   # old news: the UN datasets already cover the past
        why, unmet = str(n.get("why") or "")[:400], str(n.get("unmet") or "")[:300]
        if not shows_gap(why, unmet):
            continue   # aid handed out, or no sign anyone still lacks it: not an unmet need
        sources = [{"url": s["url"], "title": str(s.get("title") or s["url"])[:200]}
                   for s in n.get("sources") or [] if isinstance(s, dict) and str(s.get("url", "")).startswith("http")][:3]
        if sources and all(any(b in s["url"] for b in BLOCKED) for s in sources):
            continue
        reached = str(n.get("reached") or "unknown").strip().lower()
        reached = reached if reached in REACHED else "unknown"
        level = LEVELS.get(str(n.get("level") or "").strip().lower(), 1)
        if reached == "partial" and level == 3:
            level = 2   # some help is arriving: high, not urgent
        page = n.get("page")
        out.append({"area": str(n["area"]).strip()[:120], "province": str(n.get("province") or "").strip()[:60], "categories": cats,
                    "level": level, "why": why, "unmet": unmet, "reached": reached, "date": when, "sources": sources,
                    "page": int(page) if isinstance(page, (int, float)) or str(page).isdigit() else None})
    return out[:15]


def _page(url: str) -> str:
    return url.split("#")[0].split("?")[0].rstrip("/").lower()


def combine(groups: list[list[dict[str, Any]]], per_source: int = PER_SOURCE) -> list[dict[str, Any]]:
    """Merge the theme searches: at most `per_source` findings per page, and one finding per area and category
    (the most serious, then the newest)."""
    pool = [it for g in groups for it in g]
    first = {"none": 0, "unknown": 1, "partial": 2}
    pool.sort(key=lambda it: (-it["level"], first.get(it.get("reached", "unknown"), 1), -it["date"].toordinal()))
    used: dict[str, int] = {}
    seen: set[tuple[str, str]] = set()
    out = []
    for it in pool:
        page = _page(it["sources"][0]["url"]) if it["sources"] else ""
        if page and used.get(page, 0) >= per_source:
            continue
        cats = [c for c in it["categories"] if (it["area"].lower(), c) not in seen]
        if not cats:
            continue
        seen.update((it["area"].lower(), c) for c in cats)
        if page:
            used[page] = used.get(page, 0) + 1
        out.append({**it, "categories": cats})
    return out


def _scan_theme(scope: str, theme: tuple[str, list[str], str], today: datetime) -> list[dict[str, Any]]:
    name, cats, hint = theme
    prompt = PROMPT.format(today=today.strftime("%d %B %Y"), theme=name, scope=scope, hint=hint, per_source=PER_SOURCE,
                           categories=", ".join(CATEGORY_TEXT[c] for c in cats), example=cats[0])
    res = llm.complete(prompt, web={"max_uses": 4, "blocked_domains": BLOCKED}, max_tokens=2500, timeout=240)
    items = parse(res.text, today.date(), allowed=cats)
    if res.citations:   # items without their own links get the pages the AI quoted
        for it in items:
            if not it["sources"]:
                it["sources"] = [{"url": c["url"], "title": c["title"]} for c in res.citations[:1]]
    return items


def scan(scope: str) -> list[dict[str, Any]]:
    """Three theme searches at the same time (food; shelter and winter; health, hygiene and education).
    A theme that fails is skipped; if all fail, the error is raised. Up to a few minutes."""
    from concurrent.futures import ThreadPoolExecutor

    today = datetime.now(timezone.utc)
    groups, errors = [], []
    with ThreadPoolExecutor(max_workers=len(THEMES)) as pool:
        futures = [pool.submit(_scan_theme, scope, t, today) for t in THEMES]
        for f in futures:
            try:
                groups.append(f.result())
            except llm.LLMError as e:
                errors.append(str(e))
    if not groups and errors:
        raise llm.LLMError(errors[0])
    return combine(groups)


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
                                 meta={"why": it["why"], "unmet": it.get("unmet", ""), "reached": it.get("reached", "unknown"),
                                       "sources": it["sources"], "area": it["area"], "model": llm.label()}))
        added += 1
    db.commit()
    where = "" if not skipped else f" ({skipped} not matched to our places)"
    sources = len({_page(it["sources"][0]["url"]) for it in items if it["sources"]})
    return f"{len(items)} needs found from {sources} sources, {added} added{where} · {llm.label()}"


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
