"""RAG knowledge base: sources, reports, text chunks with embeddings, location tags."""

import uuid
from datetime import datetime
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.base import Base, Timestamps, UUIDPk
from app.models._types import enum_col
from app.models.enums import ReportStatus, SourceKind


class Source(Base):
    """A data source the scheduler checks automatically (or 'upload' for manual files)."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[SourceKind] = mapped_column(enum_col(SourceKind), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    every_minutes: Mapped[Optional[int]] = mapped_column(Integer)   # null = on trigger / manual
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[Optional[str]] = mapped_column(Text)


class Report(UUIDPk, Timestamps, Base):
    """One document: a ReliefWeb report, an IPC PDF, a news article, an uploaded file..."""

    __tablename__ = "reports"
    __table_args__ = (UniqueConstraint("source_id", "external_id", name="uq_report_source_external"),)

    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(120))   # e.g. ReliefWeb report id
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[Optional[str]] = mapped_column(Text)
    file_url: Mapped[Optional[str]] = mapped_column(Text)
    publisher: Mapped[Optional[str]] = mapped_column(String(160))     # e.g. NDMA, PDMA KP, IPC
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)  # skip duplicates
    status: Mapped[ReportStatus] = mapped_column(enum_col(ReportStatus), default=ReportStatus.new, index=True)
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"))
    needs_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)   # read by the AI for unmet needs

    chunks: Mapped[list["ReportChunk"]] = relationship(back_populates="report", cascade="all, delete-orphan")


class ReportChunk(UUIDPk, Base):
    """About 500 words of a report, with its embedding for vector search (pgvector)."""

    __tablename__ = "report_chunks"

    report_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    page: Mapped[Optional[int]] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    embedding = mapped_column(Vector(settings.EMBEDDING_DIM))

    report: Mapped[Report] = relationship(back_populates="chunks")
    locations: Mapped[list["ChunkLocation"]] = relationship(cascade="all, delete-orphan")


class ChunkLocation(Base):
    """Which places a chunk talks about. Auto-tagged, can be corrected by an admin."""

    __tablename__ = "chunk_locations"

    chunk_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("report_chunks.id", ondelete="CASCADE"), primary_key=True)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id"), primary_key=True, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    confirmed_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"))
