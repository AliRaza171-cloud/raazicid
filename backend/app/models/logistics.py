"""Rider jobs and live GPS pings."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPk
from app.models._types import enum_col
from app.models.enums import JobStatus

class Job(UUIDPk, Timestamps, Base):
    """One rider assignment for one donation. A reassignment creates a new Job."""

    __tablename__ = "jobs"

    donation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("donations.id", ondelete="CASCADE"), index=True)
    rider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[JobStatus] = mapped_column(enum_col(JobStatus), default=JobStatus.assigned, index=True)
    assigned_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    recommendation_score: Mapped[Optional[float]] = mapped_column(Float)   # from the rider-recommendation algorithm
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    picked_up_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    replaces_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("jobs.id"))
    decline_reason: Mapped[Optional[str]] = mapped_column(Text)

    donation = relationship("Donation", back_populates="jobs")


class RiderPing(Base):
    """GPS point sent by the rider app every 15 s during an active job."""

    __tablename__ = "rider_pings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
