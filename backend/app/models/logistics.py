"""Distribution points, rider jobs, live GPS pings and point requests."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPk
from app.models._types import enum_col
from app.models.enums import JobStatus, PointType, RequestStatus

# Which categories each point accepts (many-to-many)
point_categories = Table(
    "point_categories",
    Base.metadata,
    Column("point_id", ForeignKey("distribution_points.id", ondelete="CASCADE"), primary_key=True),
    Column("category_id", ForeignKey("categories.id"), primary_key=True),
)


class DistributionPoint(UUIDPk, Timestamps, Base):
    """A place in a needy area where our riders drop donations and our team hands them out."""

    __tablename__ = "distribution_points"

    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[PointType] = mapped_column(enum_col(PointType))
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id"), index=True)   # area
    address: Mapped[str] = mapped_column(Text)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    contact_name: Mapped[Optional[str]] = mapped_column(String(120))
    contact_phone: Mapped[Optional[str]] = mapped_column(String(20))
    same_day_food: Mapped[bool] = mapped_column(Boolean, default=False)   # can hand out cooked food the same day
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    closes_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))   # temporary relief camps
    alert_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("disaster_alerts.id"))  # set if opened for a disaster

    categories = relationship("Category", secondary=point_categories)


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


class PointRequest(UUIDPk, Timestamps, Base):
    """What people at a point are asking for. The freshest need signal we have."""

    __tablename__ = "point_requests"

    point_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("distribution_points.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    note: Mapped[Optional[str]] = mapped_column(Text)
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    status: Mapped[RequestStatus] = mapped_column(enum_col(RequestStatus), default=RequestStatus.open, index=True)
