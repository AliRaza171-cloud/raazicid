"""Report reader: the AI reads each report in the library once and lists the UNMET needs it states, per district.

Reports come from ReliefWeb (UN agencies and NGOs), uploads and saved web pages. Unlike the web scan, the AI reads the
report's own text, so findings carry a quote and a page number, and no web search is needed (about a cent a report).
Findings become "report_need" indicators: they raise need levels in Needs by area and show up in the need finder.
Same rules as the web scan: a quote that shows the gap is required, and aid already handed out is not a need.
"""

import re
import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import Category, NeedIndicator, Report, ReportChunk
from app.models.enums import ReportStatus
from app.services import llm
from app.services.gazetteer import find_places, load_places
from app.services.sources.ai_needs import CATEGORY_TEXT, GAP, SLUGS, parse

MAX_CHARS = 40_000        # about 10k words: long reports are trimmed to the passages most likely to describe needs
REPORT_MAX_AGE_DAYS = 730  # reports keep their value longer than news; need levels down-weight them after a year
NEED_WORDS = re.compile(r"\b(need|gap|shortage|lack|waiting|without|unmet|priority|priorities|require|food|shelter|hygiene|"
                        r"school|education|blanket|winter|nutrition|displaced|affected|vulnerable)\w*", re.I)

PROMPT = """Below is a report about Pakistan: "{title}" by {publisher}, dated {date}.
Read it and list the UNMET needs it states: people who still lack something, by district or city.

RAAZICID is a charity that collects and hands out goods. Only these needs count:
{categories}.

Reply with JSON only, inside ```json fences:
{{"needs": [{{
  "area": "district or city in Pakistan",
  "province": "province",
  "categories": ["hygiene"],
  "level": "urgent | high | some",
  "why": "one plain sentence: who still lacks what, with the report's numbers",
  "unmet": "a short quote from the report that shows the gap",
  "reached": "none | partial | unknown  (has any aid reached these people yet?)",
  "page": 4,
  "date": "YYYY-MM-DD if the report dates this need, otherwise leave out"
}}]}}
Rules:
- Only needs the report states. Never guess numbers or places. Use the page number shown as [page N] before the text.
- Aid that was distributed, provided or delivered is NOT a need, unless the report says people still lack it.
- Every item needs an "unmet" quote. No quote, no item.
- "urgent": many people lack it now and no aid has reached them. "high": a clear, large gap. "some": a smaller gap.
- At most 12 items, most serious first. If the report states no unmet needs for these items, reply {{"needs": []}}.

REPORT:
{text}"""


def pick_text(chunks: list[tuple[Optional[int], str]], limit: int = MAX_CHARS) -> str:
    """The report's text with page markers. Long reports: the passages that talk most about needs, in page order."""
    marked = [(i, page, f"[page {page}]\n{text}" if page else text) for i, (page, text) in enumerate(chunks)]
    if sum(len(m) for _, _, m in marked) <= limit:
        return "\n\n".join(m for _, _, m in marked)
    ranked = sorted(marked, key=lambda x: -(len(NEED_WORDS.findall(x[2])) + 3 * len(GAP.findall(x[2]))))
    keep, size = set(), 0
    for i, _, m in ranked:
        if size + len(m) > limit:
            continue
        keep.add(i)
        size += len(m)
    return "\n\n".join(m for i, _, m in marked if i in keep)


def read_report(db: Session, report_id: uuid.UUID) -> str:
    """Ask the AI for the report's unmet needs and store them (replacing any earlier reading). Returns a status line."""
    r = db.get(Report, report_id)
    if r is None:
        raise ValueError("Report not found")
    chunks = [(c.page, c.text) for c in db.scalars(select(ReportChunk).where(ReportChunk.report_id == r.id).order_by(ReportChunk.chunk_index))]
    title, publisher = r.title, r.publisher or "unknown publisher"
    published = (r.published_at or r.created_at).date()
    db.commit()   # no open transaction during the AI call
    if not chunks:
        return "No text to read (link only)"
    prompt = PROMPT.format(title=title, publisher=publisher, date=published.isoformat(), text=pick_text(chunks),
                           categories=", ".join(CATEGORY_TEXT[c] for c in SLUGS))
    res = llm.complete(prompt, max_tokens=2500, timeout=180)
    items = parse(res.text, max_age_days=REPORT_MAX_AGE_DAYS, default_date=published)
    return save(db, report_id, items)


def save(db: Session, report_id: uuid.UUID, items: list[dict[str, Any]]) -> str:
    r = db.get(Report, report_id)
    db.execute(delete(NeedIndicator).where(NeedIndicator.report_id == report_id, NeedIndicator.indicator == "report_need"))
    places = load_places(db)
    cat_ids = {c.slug: c.id for c in db.scalars(select(Category))}
    added, skipped = 0, 0
    for it in items:
        found = find_places(f"{it['area']}, {it['province']}", places) or find_places(it["province"], places)
        if not found:
            skipped += 1
            continue
        for slug in it["categories"]:
            db.add(NeedIndicator(location_id=found[0].id, category_id=cat_ids.get(slug), indicator="report_need", value=it["level"],
                                 period_start=it["date"], period_end=it["date"], source_id=r.source_id, report_id=r.id,
                                 meta={"why": it["why"], "unmet": it.get("unmet", ""), "reached": it.get("reached", "unknown"),
                                       "page": it.get("page"), "area": it["area"], "title": r.title[:200],
                                       "publisher": r.publisher, "url": r.url, "model": llm.label()}))
        added += 1
    r.needs_checked_at = datetime.now(timezone.utc)
    db.commit()
    extra = f", {skipped} not matched to our places" if skipped else ""
    return f"{len(items)} unmet needs found, {added} added{extra}"


def waiting(db: Session) -> int:
    """Reports with text that the AI has not read for needs yet."""
    has_text = select(ReportChunk.report_id).distinct()
    return db.scalar(select(func.count()).select_from(Report).where(Report.needs_checked_at.is_(None), Report.status != ReportStatus.archived,
                                                                   Report.id.in_(has_text))) or 0


def read_waiting(db: Session, limit: int = 10) -> str:
    """Read up to `limit` reports not read yet, newest first. A report that fails is skipped (and tried next time)."""
    if not llm.available():
        return "AI not set up"
    has_text = select(ReportChunk.report_id).distinct()
    ids = list(db.scalars(select(Report.id).where(Report.needs_checked_at.is_(None), Report.status != ReportStatus.archived,
                                                   Report.id.in_(has_text))
                          .order_by(func.coalesce(Report.published_at, Report.created_at).desc()).limit(limit)))
    db.commit()
    done, needs, failed = 0, 0, 0
    for rid in ids:
        try:
            status = read_report(db, rid)
            done += 1
            m = re.match(r"(\d+) unmet", status)
            needs += int(m.group(1)) if m else 0
        except Exception:   # one bad report must not stop the rest
            db.rollback()
            failed += 1
    left = waiting(db)
    return f"Read {done} reports, {needs} unmet needs found" + (f", {failed} failed" if failed else "") + (f", {left} still waiting" if left else "")


def report_findings(db: Session, report_id: uuid.UUID) -> list[dict[str, Any]]:
    """What the reader found in one report (for the Report library page)."""
    cats = {c.id: c.name for c in db.scalars(select(Category))}
    out = []
    for ind in db.scalars(select(NeedIndicator).where(NeedIndicator.report_id == report_id, NeedIndicator.indicator == "report_need")):
        m = ind.meta or {}
        out.append({"area": m.get("area"), "category": cats.get(ind.category_id, "?"), "level": int(ind.value), "why": m.get("why"),
                    "unmet": m.get("unmet"), "reached": m.get("reached"), "page": m.get("page"),
                    "date": ind.period_end.isoformat() if ind.period_end else None})
    return sorted(out, key=lambda x: (-x["level"], x["area"] or ""))


def stale(published: Optional[date]) -> bool:
    return bool(published and (datetime.now(timezone.utc).date() - published).days > REPORT_MAX_AGE_DAYS)
