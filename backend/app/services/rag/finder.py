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
from app.models import Category, Location, NeedIndicator, NeedLevel
from app.services.claude import ClaudeError, ask_complete, extract_json, search_results, text_and_citations
from app.services.gazetteer import find_places, load_places
from app.services.locations import descendant_ids, location_path
from app.services.needs import LEVEL_NAMES
from app.services.rag.search import Hit, keywords, query_vector, search
from app.services.sources import reliefweb
from app.services.sources.hapi_un import category_sectors

WEB_DOMAINS = None   # None = any site; Claude is told to prefer official and humanitarian sources
LEVEL_WORDS = {"urgent": 3, "high": 2, "some": 1}
WEB_MODES = ("auto", "always", "off")
AUTO_WEB_BELOW = 3   # "auto": search the web when the library has fewer good passages than this
WEB_SEARCHES = 4     # web searches Claude may run per question (about 1 cent each)


def use_web(mode: str, hits: list) -> bool:
    """Should this question also search the web?"""
    if mode == "always":
        return True
    if mode == "off":
        return False
    strong = [h for h in hits if "words" in h.how or h.score >= 0.02]   # found by the words, or ranked high by meaning
    return len(strong) < AUTO_WEB_BELOW

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


def un_facts(db: Session, location_id: Optional[uuid.UUID], category_id: Optional[int], start: int, limit: int = 6) -> list[dict]:
    """Who works where (OCHA 3W) for the places with the highest need, as facts [Dn]. Empty without 3W data."""
    stmt = select(NeedIndicator, Location).join(Location, Location.id == NeedIndicator.location_id).where(NeedIndicator.indicator == "orgs_present")
    if location_id:
        stmt = stmt.where(NeedIndicator.location_id.in_(descendant_ids(db, location_id)))
    rows = db.execute(stmt).all()
    if not rows:
        return []
    cat = db.get(Category, category_id) if category_id else None
    need_stmt = select(NeedLevel.location_id, NeedLevel.score).where(NeedLevel.location_id.in_([loc.id for _, loc in rows]))
    if category_id:
        need_stmt = need_stmt.where(NeedLevel.category_id == category_id)
    score: dict[uuid.UUID, float] = {}
    for lid, sc in db.execute(need_stmt).all():
        score[lid] = max(sc, score.get(lid, 0))
    rows.sort(key=lambda r: -score.get(r[1].id, 0))
    out = []
    for i, (ind, loc) in enumerate(rows[:limit]):
        sectors: dict[str, list[str]] = (ind.meta or {}).get("sectors") or {}
        if cat:
            relevant = category_sectors(cat.slug, list(sectors))
            text = (f"organisations working on {cat.name.lower()}: " + "; ".join(f"{s} ({', '.join(sectors[s][:5])})" for s in relevant)
                    if relevant else f"no organisation reported working on {cat.name.lower()} here")
        else:
            top = sorted(sectors.items(), key=lambda kv: -len(kv[1]))[:4]
            text = f"{int(ind.value)} organisations work here, e.g. " + "; ".join(f"{s}: {', '.join(o[:4])}" for s, o in top)
        out.append({"id": f"D{start + i}", "location_id": str(loc.id), "place": " › ".join(location_path(db, loc.id)),
                    "category": "Who works here", "level": "", "score": 0, "kind": "3w",
                    "text": f"{text} (OCHA 3W via HDX{', ' + ind.period_end.strftime('%b %Y') if ind.period_end else ''})", "why": ""})
    return out


def reliefweb_lookup(db: Session, query: str) -> int:
    """Add the most relevant recent ReliefWeb reports for this question to the library (when the appname is set).
    Returns how many were new. Never fails the question."""
    if not reliefweb.enabled():
        return 0
    try:
        items = reliefweb.search(" ".join(keywords(query)) or query, limit=5)
        before = len(items)
        reliefweb.sync(db, items)
        return before
    except Exception:
        db.rollback()
        return 0


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
    parts.append("\n## RAAZICID need levels (from IPC, food prices, poverty, OCHA people in need, rainfall, disaster alerts and "
                 "point requests) and who already works where (OCHA 3W). A place with high need and no organisation working "
                 "on it is a gap RAAZICID could fill: say so when it applies.")
    if facts:
        for f in facts:
            if f.get("kind") == "3w":
                parts.append(f"[{f['id']}] {f['place']}: {f['text']}")
            else:
                parts.append(f"[{f['id']}] {f['place']}: {f['category']} need is {f['level']} (score {f['score']}). {f['why']}")
    else:
        parts.append("(no need levels for this place yet)")
    if web:
        parts.append("\nSearch the web for recent information about this question in Pakistan (last few months first). "
                     "Prefer UN agencies working in Pakistan (UNICEF for education and children, WHO for health, WFP for "
                     "food, UNHCR for refugees, OCHA and NDMA / PDMA for disasters, UNDP, UNFPA, IOM, FAO), ReliefWeb, NGOs "
                     "and major Pakistani news "
                     "(Dawn, Express Tribune, The News, Geo). Combine what you find with the library passages above.")
    parts.append("\n" + FORMAT)
    return "\n\n".join(parts)


def web_list(cites: list[dict], searched: list[dict]) -> list[dict]:
    """Pages Claude quoted first (with the quote), then other pages the search found."""
    out, seen = [], set()
    for c in cites:
        if c["url"] not in seen:
            seen.add(c["url"])
            out.append({"url": c["url"], "title": c["title"], "snippet": c.get("cited_text", "")[:300], "cited": True})
    for r in searched:
        if r["url"] not in seen:
            seen.add(r["url"])
            out.append({"url": r["url"], "title": r["title"], "snippet": "", "cited": False, "age": r.get("page_age", "")})
    return out[:12]


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
               web: str = "auto") -> dict[str, Any]:
    """web: "auto" (search the web when the library has little on this), "always" or "off"."""
    web = web if web in WEB_MODES else "auto"
    db.commit()   # close the transaction left open by the login check: slow steps below must not hold one
    place = " › ".join(location_path(db, location_id)) if location_id else None
    cat = db.get(Category, category_id) if category_id else None
    cat_name = cat.name if cat else None   # plain values: reading ORM objects after a commit would reopen a transaction
    query = " ".join(x for x in [question, cat_name or "", place.split(" › ")[-1] if place else ""] if x)
    db.commit()
    from_reliefweb = reliefweb_lookup(db, query)   # live UN / NGO reports into the library first (needs the appname)
    qvec = query_vector(query)
    hits = search(db, query, location_id, k=8, qvec=qvec)
    facts = need_facts(db, location_id, category_id)
    facts += un_facts(db, location_id, category_id, start=len(facts) + 1)
    db.commit()   # Neon closes connections idle inside a transaction; Claude (with web search) can take minutes

    sources = [{"id": f"S{i}", "report_id": str(h.report_id), "chunk_id": str(h.chunk_id), "title": h.title,
                "publisher": h.publisher or h.source, "url": h.url, "page": h.page,
                "date": h.published_at.isoformat() if h.published_at else None, "text": h.text, "places": h.places,
                "found_by": h.how} for i, h in enumerate(hits, start=1)]
    base = {"question": question, "place": place, "category": cat_name, "sources": sources,
            "facts": facts, "web_results": [], "used_web": False, "web_mode": web, "model": settings.CLAUDE_MODEL,
            "reliefweb_checked": reliefweb.enabled(), "reliefweb_found": from_reliefweb}

    if not settings.ANTHROPIC_API_KEY:
        msg = "Claude is not set up (add ANTHROPIC_API_KEY), so here are the most relevant passages and our need levels."
        return {**base, "answer": msg, "summary": msg, "points": [], "note": "", "areas": [], "confidence": "low", "ai": False}

    web_search = use_web(web, hits)
    base["web_mode"] = web
    tools = None
    if web_search:
        tool: dict[str, Any] = {"type": "web_search_20250305", "name": "web_search", "max_uses": WEB_SEARCHES}
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
            "web_results": web_list(cites, search_results(res)),
            "used_web": bool(web_search),
            "ai": True}
