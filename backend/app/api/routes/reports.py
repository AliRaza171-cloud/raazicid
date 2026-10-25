"""Report library and need finder (Phase 6B). Admin only."""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import require_roles
from app.core.errors import api_error
from app.db.session import get_db
from app.models import ChunkLocation, Location, Report, ReportChunk, Source, User
from app.models.enums import ReportStatus, Role, SourceKind
from app.services.locations import location_path
from app.services.rag import embed as embedding
from app.services.rag.finder import find_needs
from app.services.rag.ingest import IngestError, add_report, fetch_page, fill_report, prepare
from app.services.rag.text import pdf_pages

router = APIRouter(tags=["reports"])
admin_only = require_roles(Role.admin)


# ---------- shapes ----------

class TagOut(BaseModel):
    id: uuid.UUID
    name: str
    path: list[str]
    confidence: float
    confirmed: bool


class ReportItem(BaseModel):
    id: uuid.UUID
    title: str
    publisher: Optional[str]
    url: Optional[str]
    source: str
    source_kind: SourceKind
    status: ReportStatus
    published_at: Optional[datetime]
    created_at: datetime
    chunks: int
    places: list[str]
    has_text: bool


class ChunkOut(BaseModel):
    id: uuid.UUID
    index: int
    page: Optional[int]
    text: str
    has_embedding: bool
    places: list[TagOut]


class ReportDetail(ReportItem):
    chunk_list: list[ChunkOut]


class LinkIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    title: Optional[str] = Field(default=None, max_length=300)
    publisher: Optional[str] = Field(default=None, max_length=160)


class TagsIn(BaseModel):
    location_ids: list[uuid.UUID] = Field(max_length=20)


class AskIn(BaseModel):
    question: str = Field(min_length=5, max_length=600)
    location_id: Optional[uuid.UUID] = None
    category_id: Optional[int] = None
    web_search: bool = False


# ---------- helpers ----------

def _items(db: Session, reports: list[Report]) -> list[ReportItem]:
    ids = [r.id for r in reports]
    if not ids:
        return []
    counts = dict(db.execute(select(ReportChunk.report_id, func.count()).where(ReportChunk.report_id.in_(ids))
                             .group_by(ReportChunk.report_id)).all())
    place_rows = db.execute(select(ReportChunk.report_id, Location.name, func.count())
                            .join(ChunkLocation, ChunkLocation.chunk_id == ReportChunk.id)
                            .join(Location, Location.id == ChunkLocation.location_id)
                            .where(ReportChunk.report_id.in_(ids))
                            .group_by(ReportChunk.report_id, Location.name)).all()
    places: dict[uuid.UUID, list[tuple[int, str]]] = {}
    for rid, name, n in place_rows:
        places.setdefault(rid, []).append((n, name))
    sources = {s.id: s for s in db.scalars(select(Source))}
    out = []
    for r in reports:
        src = sources.get(r.source_id)
        out.append(ReportItem(id=r.id, title=r.title, publisher=r.publisher, url=r.url, source=src.name if src else "?",
                              source_kind=src.kind if src else SourceKind.upload, status=r.status, published_at=r.published_at,
                              created_at=r.created_at, chunks=counts.get(r.id, 0),
                              places=[n for _, n in sorted(places.get(r.id, []), key=lambda x: -x[0])[:6]],
                              has_text=counts.get(r.id, 0) > 0))
    return out


def _detail(db: Session, r: Report) -> ReportDetail:
    item = _items(db, [r])[0]
    names = {l.id: l.name for l in db.scalars(select(Location))}
    chunks = []
    for c in sorted(r.chunks, key=lambda c: c.chunk_index):
        chunks.append(ChunkOut(id=c.id, index=c.chunk_index, page=c.page, text=c.text, has_embedding=c.embedding is not None,
                               places=[TagOut(id=t.location_id, name=names.get(t.location_id, "?"), path=location_path(db, t.location_id),
                                              confidence=t.confidence, confirmed=t.confirmed_by is not None) for t in c.locations]))
    return ReportDetail(**item.model_dump(), chunk_list=chunks)


def _get(db: Session, report_id: uuid.UUID) -> Report:
    r = db.get(Report, report_id)
    if r is None:
        raise api_error(404, "report_not_found", "Report not found")
    return r


def _when(v: Optional[str]) -> Optional[datetime]:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v)
    except ValueError:
        raise api_error(422, "bad_date", "Date should look like 2026-10-24")


# ---------- library ----------

@router.get("/admin/rag/status")
def rag_status(_: User = Depends(admin_only), db: Session = Depends(get_db)):
    total = db.scalar(select(func.count()).select_from(ReportChunk)) or 0
    with_vec = db.scalar(select(func.count()).select_from(ReportChunk).where(ReportChunk.embedding.isnot(None))) or 0
    reports = db.scalar(select(func.count()).select_from(Report).where(Report.status != ReportStatus.archived)) or 0
    return {"embeddings": embedding.status(), "claude": bool(settings.ANTHROPIC_API_KEY), "reliefweb": bool(settings.RELIEFWEB_APPNAME),
            "reports": reports, "chunks": total, "chunks_with_vectors": with_vec,
            "search": "hybrid (meaning + words)" if with_vec else "keyword"}


@router.get("/admin/reports", response_model=list[ReportItem])
def list_reports(status: Optional[ReportStatus] = None, q: Optional[str] = Query(None, max_length=100),
                 limit: int = Query(100, ge=1, le=300), _: User = Depends(admin_only), db: Session = Depends(get_db)):
    stmt = select(Report).order_by(func.coalesce(Report.published_at, Report.created_at).desc()).limit(limit)
    if status:
        stmt = stmt.where(Report.status == status)
    else:
        stmt = stmt.where(Report.status != ReportStatus.archived)
    if q:
        stmt = stmt.where(Report.title.ilike(f"%{q.strip()}%"))
    return _items(db, list(db.scalars(stmt)))


@router.get("/admin/reports/{report_id}", response_model=ReportDetail)
def one_report(report_id: uuid.UUID, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    return _detail(db, _get(db, report_id))


@router.post("/admin/reports/upload", response_model=ReportDetail, status_code=201)
def upload(file: UploadFile = File(...), title: Optional[str] = Form(None), publisher: Optional[str] = Form(None),
           published_at: Optional[str] = Form(None), admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    """A PDF or text file: situation reports, IPC analyses, NGO assessments, our own field notes.
    A plain (not async) function: reading a long PDF and making vectors runs in a worker thread, not blocking the API."""
    admin_id = admin.id
    db.commit()   # no open transaction while the PDF is read and vectors are made
    name = (file.filename or "report").strip()
    data = file.file.read(settings.MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise api_error(413, "too_big", f"Files up to {settings.MAX_UPLOAD_MB} MB")
    lower = name.lower()
    is_pdf = lower.endswith(".pdf") or data[:5] == b"%PDF-"
    if not is_pdf and not lower.endswith((".txt", ".md", ".csv")):
        raise api_error(422, "bad_file", "Upload a PDF or a .txt file")
    try:
        pages = pdf_pages(data) if is_pdf else [(None, data.decode("utf-8", errors="replace"))]
    except Exception:   # damaged or password-protected PDF
        raise api_error(422, "unreadable", "This file could not be read. Is it a real PDF without a password?")
    if not pages:
        raise api_error(422, "no_text", "No text found. Scanned PDFs (photos of pages) cannot be read yet.")
    clean_title = (title or "").strip() or name.rsplit(".", 1)[0].replace("_", " ").replace("-", " ")
    try:
        r, created = add_report(db, kind=SourceKind.upload, title=clean_title, pages=pages, publisher=(publisher or "").strip() or None,
                                published_at=_when(published_at), uploaded_by=admin_id)
    except IngestError as e:
        raise api_error(422, "unreadable", str(e))
    if not created:
        raise api_error(409, "duplicate", f"Already in the library: {r.title}")
    return _detail(db, r)


@router.post("/admin/reports/link", response_model=ReportDetail, status_code=201)
def add_link(body: LinkIn, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    """Read a news article, NDMA / PDMA page or online PDF and add its text."""
    admin_id = admin.id
    db.commit()
    try:
        page_title, pages, host = fetch_page(body.url)
        r, created = add_report(db, kind=SourceKind.upload, title=body.title or page_title or body.url, pages=pages, url=body.url.strip(),
                                publisher=body.publisher or host, uploaded_by=admin_id)
    except IngestError as e:
        raise api_error(422, "unreadable", str(e))
    if not created:
        raise api_error(409, "duplicate", f"Already in the library: {r.title}")
    return _detail(db, r)


@router.post("/admin/reports/{report_id}/fetch", response_model=ReportDetail)
def fetch_text(report_id: uuid.UUID, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    """Read the text of a link saved by the news scan or GDACS, so the need finder can use it."""
    r = _get(db, report_id)
    if not r.url:
        raise api_error(422, "no_link", "This report has no link")
    url, title = r.url, r.title
    db.commit()   # the page download and vectors happen outside a transaction
    try:
        _, pages, _host = fetch_page(url)
        prepared = prepare(title, pages)
        r = _get(db, report_id)
        fill_report(db, r, pages, prepared)
        db.commit()
    except IngestError as e:
        db.rollback()
        raise api_error(422, "unreadable", str(e))
    db.refresh(r)
    return _detail(db, r)


@router.put("/admin/chunks/{chunk_id}/places", response_model=ChunkOut)
def set_places(chunk_id: uuid.UUID, body: TagsIn, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    """Correct which places a passage is about (wrong or missing auto-tags)."""
    c = db.get(ReportChunk, chunk_id)
    if c is None:
        raise api_error(404, "chunk_not_found", "Passage not found")
    if any(db.get(Location, i) is None for i in body.location_ids):
        raise api_error(422, "bad_location", "Choose places from the list")
    c.locations = [ChunkLocation(location_id=i, confidence=1.0, confirmed_by=admin.id) for i in dict.fromkeys(body.location_ids)]
    report = c.report
    db.flush()
    report.status = ReportStatus.tagged if any(ch.locations for ch in report.chunks) else ReportStatus.needs_review
    db.commit()
    names = {l.id: l.name for l in db.scalars(select(Location).where(Location.id.in_(body.location_ids)))}
    return ChunkOut(id=c.id, index=c.chunk_index, page=c.page, text=c.text, has_embedding=c.embedding is not None,
                    places=[TagOut(id=t.location_id, name=names.get(t.location_id, "?"), path=location_path(db, t.location_id),
                                   confidence=t.confidence, confirmed=True) for t in c.locations])


@router.post("/admin/reports/{report_id}/archive", response_model=ReportItem)
def archive(report_id: uuid.UUID, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    """Out of date or wrong: the need finder stops using it. Can be restored."""
    r = _get(db, report_id)
    r.status = ReportStatus.archived
    db.commit()
    return _items(db, [r])[0]


@router.post("/admin/reports/{report_id}/restore", response_model=ReportItem)
def restore(report_id: uuid.UUID, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    r = _get(db, report_id)
    r.status = ReportStatus.tagged if any(c.locations for c in r.chunks) else ReportStatus.needs_review
    db.commit()
    return _items(db, [r])[0]


@router.post("/admin/rag/embed-missing")
def embed_missing(_: User = Depends(admin_only), db: Session = Depends(get_db)):
    """After installing sentence-transformers: add vectors to passages stored without one."""
    rows = db.execute(select(ReportChunk.id, Report.title, ReportChunk.text).join(Report, Report.id == ReportChunk.report_id)
                      .where(ReportChunk.embedding.is_(None)).limit(2000)).all()
    if not rows:
        return {"done": 0, "note": "Every passage already has a vector"}
    db.commit()   # making vectors can take a while: no open transaction meanwhile
    vecs = embedding.embed([f"{title}\n{text}" for _, title, text in rows])
    if vecs is None:
        raise api_error(503, "embeddings_off", embedding.status()["note"])
    for (cid, _, _), v in zip(rows, vecs):
        db.get(ReportChunk, cid).embedding = v
    db.commit()
    return {"done": len(rows), "note": f"Added vectors to {len(rows)} passages"}


# ---------- need finder ----------

@router.post("/admin/need-finder/ask")
def need_finder(body: AskIn, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    if body.location_id and db.get(Location, body.location_id) is None:
        raise api_error(422, "bad_location", "Choose the place from the list")
    return find_needs(db, " ".join(body.question.split()), body.location_id, body.category_id, body.web_search)
