"""Need finder: answer "where is X needed?" from our report library, our need levels and (optionally) the web.

Retrieval-augmented generation:
  1. find the most relevant passages in the library (hybrid search, filtered by place)
  2. add our computed need levels for that place as structured facts
  3. Claude answers using only those sources (and web search if switched on), citing every claim
  4. the areas it names are matched to our places, so the admin can open them on the map or send an appeal
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Category, Location, NeedLevel
from app.services.claude import ClaudeError, ask_complete, extract_json, text_and_citations
from app.services.gazetteer import find_places, load_places
from app.services.locations import descendant_ids, location_path
from app.services.needs import LEVEL_NAMES
from app.services.rag.search import Hit, search

WEB_DOMAINS = None   # None = any site; Claude is told to prefer official and humanitarian sources
LEVEL_WORDS = {"urgent": 3, "high": 2, "some": 1}

SYSTEM = """You are the need finder for RAAZICID, a donation charity in Pakistan that collects goods (food, rations,
clothes, blankets, winter items, hygiene kits, baby items, household items, school supplies, books, mobility aids,
emergency relief) and hands them out through its own distribution points and relief camps.

Answer the admin's question using ONLY the sources given (and web search results if you search).
- Every factual sentence must cite its source in square brackets, e.g. [S2] or [D1]. Web facts are cited automatically.
- Never invent numbers, places or dates. If the sources do not answer the question, say so plainly.
- Prefer recent sources. Mention the date when it matters.
- Name specific districts, cities or areas in Pakistan wherever the sources allow.
- Keep the answer short: 3 to 6 sentences, plain English."""

FORMAT = """Reply with JSON only, inside ```json fences:
{"answer": "short answer with [S1]-style citations",
 "areas": [{"name": "district / city / area in Pakistan", "need": "urgent | high | some",
            "categories": ["Blankets", "Food"], "reason": "one sentence with citations", "sources": ["S1", "D2"]}],
 "confidence": "low | medium | high"}
List at most 6 areas, most needed first. Use an empty list if the sources name no areas."""


def _fmt_date(d: Optional[datetime]) -> str:
    return d.strftime("%d %b %Y") if d else "date unknown"


def need_facts(db: Session, location_id: Optional[uuid.UUID], category_id: Optional[int], limit: int = 12) -> list[dict]:
    """Our own computed need levels as numbered facts [D1], [D2]..."""
    cats = {c.id: c.name for c in db.scalars(select(Category))}
    stmt = select(NeedLevel, Location).join(Location, Location.id == NeedLevel.location_id).where(NeedLevel.level >= 1)
    if location_id:
        stmt = stmt.where(NeedLevel.location_id.in_(descendant_ids(db, location_id)))
    if category_id:
        stmt = stmt.where(NeedLevel.category_id == category_id)
    rows = db.execute(stmt.order_by(NeedLevel.score.desc()).limit(limit)).all()
    out = []
    for i, (nl, loc) in enumerate(rows, start=1):
        why = "; ".join(f"{r.get('why')} ({r.get('source')}{', ' + r['date'] if r.get('date') else ''})" for r in (nl.reasons or [])[:3])
        out.append({"id": f"D{i}", "location_id": str(loc.id), "place": " › ".join(location_path(db, loc.id)),
                    "category": cats.get(nl.category_id, "?"), "level": LEVEL_NAMES[nl.level], "score": round(nl.score),
                    "why": why})
    return out


def build_prompt(question: str, place: Optional[str], category: Optional[str], hits: list[Hit], facts: list[dict], web: bool) -> str:
    parts = [f"Today is {datetime.now(timezone.utc).strftime('%d %B %Y')}.", f"Question: {question}"]
    if place:
        parts.append(f"Focus on: {place}, Pakistan")
    if category:
        parts.append(f"Category: {category}")
    parts.append("\n## Report library passages")
    if hits:
        for i, h in enumerate(hits, start=1):
            where = f", page {h.page}" if h.page else ""
            tags = f" · places: {', '.join(h.places)}" if h.places else ""
            parts.append(f"[S{i}] {h.title} ({h.publisher or h.source}, {_fmt_date(h.published_at)}{where}){tags}\n{h.text}")
    else:
        parts.append("(no matching passages in the library)")
    parts.append("\n## RAAZICID need levels (computed from IPC, food prices, poverty, disaster alerts and point requests)")
    if facts:
        for f in facts:
            parts.append(f"[{f['id']}] {f['place']}: {f['category']} need is {f['level']} (score {f['score']}). {f['why']}")
    else:
        parts.append("(no need levels for this place yet)")
    if web:
        parts.append("\nYou may search the web for recent information (NDMA, PDMA, PMD, ReliefWeb, UN agencies, major Pakistani news).")
    parts.append("\n" + FORMAT)
    return "\n\n".join(parts)


def _cited(text: str) -> set[str]:
    return set(re.findall(r"\[((?:S|D)\d+)\]", text or ""))


def match_areas(db: Session, areas: list[dict], category_id: Optional[int]) -> list[dict]:
    """Attach our place id, path and current need level to each area Claude named."""
    places = load_places(db)
    out = []
    for a in areas[:6]:
        if not isinstance(a, dict) or not a.get("name"):
            continue
        found = find_places(str(a["name"]), places)
        loc = found[0] if found else None
        level = None
        if loc:
            stmt = select(NeedLevel).where(NeedLevel.location_id.in_(descendant_ids(db, loc.id)))
            if category_id:
                stmt = stmt.where(NeedLevel.category_id == category_id)
            best = max(db.scalars(stmt), key=lambda n: n.score, default=None)
            level = best.level if best else 0
        out.append({
            "name": str(a["name"])[:120],
            "need": a.get("need") if a.get("need") in LEVEL_WORDS else "some",
            "categories": [str(c)[:60] for c in (a.get("categories") or [])][:6],
            "reason": str(a.get("reason") or "")[:600],
            "sources": [s for s in (a.get("sources") or []) if isinstance(s, str) and re.fullmatch(r"[SD]\d+", s)],
            "location_id": str(loc.id) if loc else None,
            "path": location_path(db, loc.id) if loc else [],
            "our_level": level,
        })
    return out


def find_needs(db: Session, question: str, location_id: Optional[uuid.UUID] = None, category_id: Optional[int] = None,
               web_search: bool = False) -> dict[str, Any]:
    place = " › ".join(location_path(db, location_id)) if location_id else None
    cat = db.get(Category, category_id) if category_id else None
    query = " ".join(x for x in [question, cat.name if cat else "", place.split(" › ")[-1] if place else ""] if x)
    hits = search(db, query, location_id, k=8)
    facts = need_facts(db, location_id, category_id)

    sources = [{"id": f"S{i}", "report_id": str(h.report_id), "chunk_id": str(h.chunk_id), "title": h.title,
                "publisher": h.publisher or h.source, "url": h.url, "page": h.page,
                "date": h.published_at.isoformat() if h.published_at else None, "text": h.text, "places": h.places,
                "found_by": h.how} for i, h in enumerate(hits, start=1)]
    base = {"question": question, "place": place, "category": cat.name if cat else None, "sources": sources,
            "facts": facts, "web_results": [], "used_web": False, "model": settings.CLAUDE_MODEL}

    if not settings.ANTHROPIC_API_KEY:
        return {**base, "answer": "Claude is not set up (add ANTHROPIC_API_KEY), so here are the most relevant passages and "
                                  "our need levels without a written answer.", "areas": [], "confidence": "low", "ai": False}

    tools = None
    if web_search:
        tool: dict[str, Any] = {"type": "web_search_20250305", "name": "web_search", "max_uses": 3}
        if WEB_DOMAINS:
            tool["allowed_domains"] = WEB_DOMAINS
        tools = [tool]
    try:
        res = ask_complete([{"role": "user", "content": build_prompt(question, place, cat.name if cat else None, hits, facts, web_search)}],
                  system=SYSTEM, tools=tools, max_tokens=2000, timeout=150)
    except ClaudeError as e:
        return {**base, "answer": f"Claude could not answer just now ({e}). The passages and need levels below are still useful.",
                "areas": [], "confidence": "low", "ai": False}

    text, cites = text_and_citations(res)
    try:
        data = extract_json(text)
        if not isinstance(data, dict):
            raise ValueError
    except ValueError:
        data = {"answer": text.strip()[:3000], "areas": [], "confidence": "low"}

    answer = str(data.get("answer") or "").strip()
    used = _cited(answer) | {s for a in data.get("areas") or [] if isinstance(a, dict) for s in (a.get("sources") or []) if isinstance(s, str)}
    for s in sources:
        s["cited"] = s["id"] in used
    return {**base,
            "answer": answer,
            "areas": match_areas(db, data.get("areas") or [], category_id),
            "confidence": data.get("confidence") if data.get("confidence") in ("low", "medium", "high") else "medium",
            "web_results": [{"url": c["url"], "title": c["title"], "snippet": c.get("cited_text", "")[:300]} for c in cites],
            "used_web": bool(web_search),
            "ai": True}
