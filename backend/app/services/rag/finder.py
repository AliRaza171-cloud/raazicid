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
from app.services.rag.search import Hit, query_vector, search

WEB_DOMAINS = None   # None = any site; Claude is told to prefer official and humanitarian sources
LEVEL_WORDS = {"urgent": 3, "high": 2, "some": 1}

SYSTEM = """You are the need finder for RAAZICID, a donation charity in Pakistan that collects goods (food, rations,
clothes, blankets, winter items, hygiene kits, baby items, household items, school supplies, books, mobility aids,
emergency relief) and hands them out through its own distribution points and relief camps.

Answer the admin's question using ONLY the sources given (and web search results if you search).

Write for a busy charity worker, not an expert:
- Short sentences and everyday words. No jargon: say "food crisis level" instead of "IPC Phase 3+".
- Start with one plain sentence that answers the question. Then at most 4 short points.
- Every point ends with its source in square brackets: [S2] for a library passage, [D1] for our need levels,
  [Web] for something you found with web search. Do not use <cite> tags or any other markup.
- Never invent numbers, places or dates. If the sources do not answer the question, say so plainly.
- Prefer recent sources and say when they are old (for example "reports from April").
- Name specific districts or cities in Pakistan wherever the sources allow."""

FORMAT = """Reply with JSON only, inside ```json fences:
{"summary": "one plain sentence that answers the question",
 "points": ["short point with its source, e.g. Rawalpindi is short of 40% of new textbooks [S1]"],
 "areas": [{"name": "district or city in Pakistan", "need": "urgent | high | some",
            "categories": ["School supplies", "Books"], "reason": "one short sentence with its source", "sources": ["S1", "D2"]}],
 "note": "one short sentence on what the sources do not cover, or empty",
 "confidence": "low | medium | high"}
At most 4 points and 5 areas, most needed first. Use the category names RAAZICID uses. Empty lists if nothing fits."""

CITE_TAG = re.compile(r"<cite\b[^>]*>(.*?)</cite>", re.S | re.I)


def tidy(text: str) -> str:
    """Plain text: web-search <cite> tags become a [Web] marker, other markup is removed, spaces tidied."""
    text = CITE_TAG.sub(lambda m: m.group(1) + "\x00", str(text or ""))
    text = re.sub(r"\x00(?=\s*[a-z0-9(%])", "", text)              # mid-sentence: the marker waits for the clause end
    text = text.replace("\x00", " [Web]")
    text = re.sub(r"</?[a-zA-Z][^>]*>", "", text)
    text = re.sub(r"(\s*\[Web\])+", " [Web]", text)              # one marker is enough
    text = re.sub(r"\[Web\]([.,;:])", r"\1 [Web]", text)          # marker after the full stop reads better
    text = re.sub(r"\s+([.,;:])", r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip()


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
    db.commit()   # close the transaction left open by the login check: slow steps below must not hold one
    place = " › ".join(location_path(db, location_id)) if location_id else None
    cat = db.get(Category, category_id) if category_id else None
    cat_name = cat.name if cat else None   # plain values: reading ORM objects after a commit would reopen a transaction
    query = " ".join(x for x in [question, cat_name or "", place.split(" › ")[-1] if place else ""] if x)
    db.commit()
    qvec = query_vector(query)
    hits = search(db, query, location_id, k=8, qvec=qvec)
    facts = need_facts(db, location_id, category_id)
    db.commit()   # Neon closes connections idle inside a transaction; Claude (with web search) can take minutes

    sources = [{"id": f"S{i}", "report_id": str(h.report_id), "chunk_id": str(h.chunk_id), "title": h.title,
                "publisher": h.publisher or h.source, "url": h.url, "page": h.page,
                "date": h.published_at.isoformat() if h.published_at else None, "text": h.text, "places": h.places,
                "found_by": h.how} for i, h in enumerate(hits, start=1)]
    base = {"question": question, "place": place, "category": cat_name, "sources": sources,
            "facts": facts, "web_results": [], "used_web": False, "model": settings.CLAUDE_MODEL}

    if not settings.ANTHROPIC_API_KEY:
        msg = "Claude is not set up (add ANTHROPIC_API_KEY), so here are the most relevant passages and our need levels."
        return {**base, "answer": msg, "summary": msg, "points": [], "note": "", "areas": [], "confidence": "low", "ai": False}

    tools = None
    if web_search:
        tool: dict[str, Any] = {"type": "web_search_20250305", "name": "web_search", "max_uses": 3}
        if WEB_DOMAINS:
            tool["allowed_domains"] = WEB_DOMAINS
        tools = [tool]
    try:
        res = ask_complete([{"role": "user", "content": build_prompt(question, place, cat_name, hits, facts, web_search)}],
                  system=SYSTEM, tools=tools, max_tokens=2000, timeout=150)
    except ClaudeError as e:
        msg = f"Claude could not answer just now ({e}). The passages and need levels below are still useful."
        return {**base, "answer": msg, "summary": msg, "points": [], "note": "", "areas": [], "confidence": "low", "ai": False}

    text, cites = text_and_citations(res)
    try:
        data = extract_json(CITE_TAG.sub(lambda m: m.group(1), text))
        if not isinstance(data, dict):
            raise ValueError
    except ValueError:
        data = {"summary": tidy(text)[:600], "points": [], "areas": [], "confidence": "low"}

    summary = tidy(data.get("summary") or data.get("answer") or "")
    points = [tidy(p) for p in (data.get("points") or []) if isinstance(p, str) and p.strip()][:4]
    note = tidy(data.get("note") or "")
    areas = []
    for a in (data.get("areas") or [])[:5]:
        if isinstance(a, dict):
            areas.append({**a, "name": tidy(a.get("name", "")), "reason": tidy(a.get("reason", "")),
                          "categories": [tidy(c) for c in a.get("categories") or [] if isinstance(c, str)]})
    answer = " ".join([summary, *points]).strip()
    used = _cited(answer) | {s for a in areas for s in (a.get("sources") or []) if isinstance(s, str)} | {x for a in areas for x in _cited(a["reason"])}
    for s in sources:
        s["cited"] = s["id"] in used
    return {**base,
            "answer": answer,
            "summary": summary,
            "points": points,
            "note": note,
            "areas": match_areas(db, areas, category_id),
            "confidence": data.get("confidence") if data.get("confidence") in ("low", "medium", "high") else "medium",
            "web_results": [{"url": c["url"], "title": c["title"], "snippet": c.get("cited_text", "")[:300]} for c in cites],
            "used_web": bool(web_search),
            "ai": True}
