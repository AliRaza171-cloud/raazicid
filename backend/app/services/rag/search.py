"""Finding the passages that answer a question.

Hybrid retrieval: vector search (pgvector cosine distance, when embeddings are on) and Postgres keyword
search, merged with reciprocal rank fusion. A place filter keeps passages tagged with that place, a place
inside it, or the province / city around it.
"""

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ChunkLocation, Location, Report, ReportChunk, Source
from app.models.enums import ReportStatus
from app.services.locations import ancestor_ids, descendant_ids
from app.services.rag.embed import embed

RRF_K = 60
STOP = set("""a an and are as at be by can do does for from has have how i in is it its me most my need needed needs
of on or our please should show tell than that the their them there these they this to was we were what when where
which who why will with would you your about any area areas place places right now currently""".split())


@dataclass
class Hit:
    chunk_id: uuid.UUID
    report_id: uuid.UUID
    title: str
    publisher: Optional[str]
    url: Optional[str]
    page: Optional[int]
    published_at: Optional[datetime]
    source: str
    text: str
    score: float = 0.0
    places: list[str] = field(default_factory=list)
    how: list[str] = field(default_factory=list)   # "meaning" and/or "words": why it was found


def keywords(question: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z\-']{2,}", question.lower())
    out: list[str] = []
    for w in words:
        w = w.strip("-'")
        if w and w not in STOP and w not in out:
            out.append(w)
    return out[:12]


def rrf(rankings: dict[str, list[uuid.UUID]]) -> dict[uuid.UUID, tuple[float, list[str]]]:
    """Reciprocal rank fusion: a passage high in either list ranks high overall."""
    out: dict[uuid.UUID, tuple[float, list[str]]] = {}
    for name, ids in rankings.items():
        for rank, cid in enumerate(ids):
            score, how = out.get(cid, (0.0, []))
            out[cid] = (score + 1.0 / (RRF_K + rank + 1), how + [name])
    return out


def _place_filter(db: Session, location_id: Optional[uuid.UUID]):
    if not location_id:
        return None
    ids = set(descendant_ids(db, location_id)) | set(ancestor_ids(db, location_id))
    return select(ChunkLocation.chunk_id).where(ChunkLocation.location_id.in_(ids))


def _base(db: Session, location_id: Optional[uuid.UUID]):
    stmt = (select(ReportChunk.id).join(Report, Report.id == ReportChunk.report_id)
            .where(Report.status != ReportStatus.archived))
    pf = _place_filter(db, location_id)
    if pf is not None:
        stmt = stmt.where(ReportChunk.id.in_(pf))
    return stmt


def vector_ids(db: Session, qvec: Optional[list[float]], location_id: Optional[uuid.UUID], limit: int) -> list[uuid.UUID]:
    if not qvec:
        return []
    dist = ReportChunk.embedding.cosine_distance(qvec)
    stmt = _base(db, location_id).where(ReportChunk.embedding.isnot(None)).order_by(dist).limit(limit)
    return list(db.scalars(stmt))


def keyword_ids(db: Session, question: str, location_id: Optional[uuid.UUID], limit: int) -> list[uuid.UUID]:
    words = keywords(question)
    if not words:
        return []
    ts = func.to_tsvector("english", ReportChunk.text)
    query = func.to_tsquery("english", " | ".join(re.sub(r"[^a-z]", "", w) for w in words if re.sub(r"[^a-z]", "", w)))
    stmt = (_base(db, location_id).where(ts.op("@@")(query))
            .order_by(func.ts_rank_cd(ts, query).desc()).limit(limit))
    return list(db.scalars(stmt))


def query_vector(question: str) -> Optional[list[float]]:
    """The question as a vector, or None (embeddings off, or the model is still loading: keyword search only)."""
    vec = embed([question], wait=False)
    return vec[0] if vec else None


def search(db: Session, question: str, location_id: Optional[uuid.UUID] = None, k: int = 8,
           qvec: Optional[list[float]] = None) -> list[Hit]:
    """Pass `qvec` (from query_vector) when you made it before opening a database transaction."""
    if qvec is None:
        qvec = query_vector(question)
    rankings = {"meaning": vector_ids(db, qvec, location_id, k * 3), "words": keyword_ids(db, question, location_id, k * 3)}
    fused = rrf(rankings)
    if location_id and len(fused) < 3:
        # Little about this place in the library: also use passages from anywhere, ranked lower
        wide = rrf({"meaning": vector_ids(db, qvec, None, k * 2), "words": keyword_ids(db, question, None, k * 2)})
        for cid, (s, how) in wide.items():
            fused.setdefault(cid, (s * 0.5, how))
    top = sorted(fused.items(), key=lambda kv: -kv[1][0])[:k]
    if not top:
        return []
    ids = [cid for cid, _ in top]
    rows = db.execute(select(ReportChunk, Report, Source.name).join(Report, Report.id == ReportChunk.report_id)
                      .join(Source, Source.id == Report.source_id).where(ReportChunk.id.in_(ids))).all()
    by_id = {c.id: (c, r, sname) for c, r, sname in rows}
    names = dict(db.execute(select(ChunkLocation.chunk_id, func.string_agg(Location.name, ", "))
                            .join(Location, Location.id == ChunkLocation.location_id)
                            .where(ChunkLocation.chunk_id.in_(ids)).group_by(ChunkLocation.chunk_id)).all())
    hits = []
    for cid, (score, how) in top:
        if cid not in by_id:
            continue
        c, r, sname = by_id[cid]
        hits.append(Hit(chunk_id=c.id, report_id=r.id, title=r.title, publisher=r.publisher, url=r.url, page=c.page,
                        published_at=r.published_at or r.created_at, source=sname, text=c.text, score=round(score, 5),
                        places=[n for n in (names.get(cid) or "").split(", ") if n], how=sorted(set(how))))
    return hits


def mentions(db: Session, location_id: uuid.UUID) -> int:
    """How many library passages talk about this place or a place inside it."""
    ids = descendant_ids(db, location_id)
    return db.scalar(select(func.count(func.distinct(ChunkLocation.chunk_id))).where(ChunkLocation.location_id.in_(ids))) or 0

