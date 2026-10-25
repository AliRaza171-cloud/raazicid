"""Adding documents to the report library: passages, place tags and embeddings."""

import hashlib
import ipaddress
import re
import socket
import uuid
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ChunkLocation, Report, ReportChunk, Source
from app.models.enums import ReportStatus, SourceKind
from app.services.gazetteer import Place, find_places, load_places
from app.services.rag.embed import embed
from app.services.rag.text import Page, chunk_pages, html_text

TITLE_TAG_CONFIDENCE = 0.6   # a passage that names no place gets the places in the report title, marked less sure


class IngestError(ValueError):
    pass


def source_id(db: Session, kind: SourceKind) -> int:
    sid = db.scalar(select(Source.id).where(Source.kind == kind))
    if sid is None:
        raise IngestError(f"Source {kind.value} is missing: run python -m app.seed.run")
    return sid


def text_hash(pages: list[Page]) -> str:
    norm = re.sub(r"\s+", " ", " ".join(t for _, t in pages)).strip().lower()
    return hashlib.sha256(f"text:{norm[:50000]}".encode()).hexdigest()


def tag_chunks(chunks: list[ReportChunk], title: str, places: list[Place]) -> int:
    """Attach places to each passage. Returns how many passages got at least one place."""
    title_places = find_places(title, places)
    tagged = 0
    for c in chunks:
        found = find_places(c.text, places)
        if found:
            c.locations = [ChunkLocation(location_id=p.id, confidence=1.0) for p in found[:12]]
        elif title_places:
            c.locations = [ChunkLocation(location_id=p.id, confidence=TITLE_TAG_CONFIDENCE) for p in title_places[:6]]
        else:
            c.locations = []
        tagged += bool(c.locations)
    return tagged


Prepared = tuple[list[dict], Optional[list[list[float]]]]


def prepare(title: str, pages: list[Page]) -> Prepared:
    """Passages and their vectors. No database work, so it may take as long as it needs (long PDFs, first model load)."""
    pieces = chunk_pages(pages)
    if not pieces:
        raise IngestError("No readable text found. Scanned PDFs (photos of pages) cannot be read yet.")
    return pieces, embed([f"{title}\n{p['text']}" for p in pieces])


def fill_report(db: Session, report: Report, pages: list[Page], prepared: Optional[Prepared] = None) -> Report:
    """Replace the report's passages with new ones from `pages`."""
    pieces, vecs = prepared or prepare(report.title, pages)
    report.chunks.clear()
    db.flush()
    chunks = [ReportChunk(chunk_index=i, page=p["page"], text=p["text"]) for i, p in enumerate(pieces)]
    if vecs:
        for c, v in zip(chunks, vecs):
            c.embedding = v
    tagged = tag_chunks(chunks, report.title, load_places(db))
    report.chunks.extend(chunks)
    report.status = ReportStatus.tagged if tagged else ReportStatus.needs_review
    return report


def add_report(db: Session, *, kind: SourceKind, title: str, pages: list[Page], url: Optional[str] = None,
               publisher: Optional[str] = None, published_at: Optional[datetime] = None,
               external_id: Optional[str] = None, uploaded_by: Optional[uuid.UUID] = None) -> tuple[Report, bool]:
    """(report, created). The same text or the same link is never stored twice."""
    title = " ".join(title.split())[:300] or "Untitled report"
    prepared = prepare(title, pages)   # before any query: no transaction is held while vectors are made
    sid = source_id(db, kind)
    if external_id:
        same = db.scalar(select(Report).where(Report.source_id == sid, Report.external_id == external_id))
        if same is not None:
            return same, False
    h = text_hash(pages)
    same = db.scalar(select(Report).where(Report.content_hash == h))
    if same is not None:
        return same, False
    # A link saved earlier without text (from the news scan or GDACS): fill that one in
    report = db.scalar(select(Report).where(Report.url == url)) if url else None
    if report is not None and report.chunks:
        return report, False
    if report is None:
        report = Report(source_id=sid, title=title, url=url, publisher=publisher, published_at=published_at,
                        external_id=external_id, uploaded_by=uploaded_by, content_hash=h)
        db.add(report)
    else:
        report.title = report.title or title
        report.publisher = report.publisher or publisher
    fill_report(db, report, pages, prepared)
    db.commit()
    db.refresh(report)
    return report, True


# ---------- web pages ----------

def check_url(url: str) -> str:
    """Only public http(s) pages: the server must not be used to reach the local network."""
    u = urlparse(url.strip())
    if u.scheme not in ("http", "https") or not u.hostname:
        raise IngestError("Use a full link starting with https://")
    host = u.hostname.lower()
    if host in ("localhost",) or host.endswith(".local") or host.endswith(".internal"):
        raise IngestError("That link points to this computer or a local network")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise IngestError("That website could not be found")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise IngestError("That link points to this computer or a local network")
    return url.strip()


def fetch_page(url: str) -> tuple[str, list[Page], Optional[str]]:
    """(title, pages, publisher) for a web page or a linked PDF."""
    url = check_url(url)
    headers = {"User-Agent": "Mozilla/5.0 (RAAZICID FYP report reader)"}
    try:
        res = httpx.get(url, headers=headers, timeout=30, follow_redirects=True)
    except httpx.HTTPError as e:
        raise IngestError(f"Could not open the link: {e}")
    if res.status_code >= 400:
        raise IngestError(f"The website answered {res.status_code}; it may block automatic reading")
    check_url(str(res.url))   # also after redirects
    publisher = (urlparse(str(res.url)).hostname or "").replace("www.", "") or None
    if "pdf" in res.headers.get("content-type", "") or str(res.url).lower().endswith(".pdf"):
        from app.services.rag.text import pdf_pages
        return "", pdf_pages(res.content), publisher
    title, text = html_text(res.text)
    if len(text.split()) < 80:
        raise IngestError("Too little text on that page (it may need a browser or a login)")
    return title, [(None, text)], publisher
