"""Disaster alerts, what each one needs, and donor appeals."""

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPk
from app.models._types import enum_col
from app.models.enums import AlertSeverity, AlertStatus, AlertType

alert_locations = Table(
    "alert_locations",
    Base.metadata,
    Column("alert_id", ForeignKey("disaster_alerts.id", ondelete="CASCADE"), primary_key=True),
    Column("location_id", ForeignKey("locations.id"), primary_key=True),
)

alert_reports = Table(
    "alert_reports",
    Base.metadata,
    Column("alert_id", ForeignKey("disaster_alerts.id", ondelete="CASCADE"), primary_key=True),
    Column("report_id", ForeignKey("reports.id"), primary_key=True),
)


class DisasterAlert(UUIDPk, Timestamps, Base):
    __tablename__ = "disaster_alerts"

    type: Mapped[AlertType] = mapped_column(enum_col(AlertType))
    severity: Mapped[AlertSeverity] = mapped_column(enum_col(AlertSeverity))
    status: Mapped[AlertStatus] = mapped_column(enum_col(AlertStatus), default=AlertStatus.unconfirmed, index=True)
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[Optional[str]] = mapped_column(Text)               # written by Claude from the sources only
    # Only figures stated in sources, never guessed: {"families_affected": 1200, "houses_damaged": 340}
    reported_figures: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    gdacs_event_id: Mapped[Optional[str]] = mapped_column(String(40), index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    confirmed_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"))
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    locations = relationship("Location", secondary=alert_locations)
    reports = relationship("Report", secondary=alert_reports)
    needs: Mapped[list["AlertNeed"]] = relationship(back_populates="alert", cascade="all, delete-orphan")


class AlertNeed(UUIDPk, Base):
    """'What is needed' table on the alert page: suggested from figures x per-family rules, editable."""

    __tablename__ = "alert_needs"

    alert_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("disaster_alerts.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    quantity_needed: Mapped[Optional[int]] = mapped_column(Integer)   # null = waiting for figures
    quantity_pledged: Mapped[int] = mapped_column(Integer, default=0)

    alert: Mapped[DisasterAlert] = relationship(back_populates="needs")


class Appeal(UUIDPk, Timestamps, Base):
    """An emergency or area appeal sent to donors in chosen provinces. Always sent by an admin."""

    __tablename__ = "appeals"

    alert_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("disaster_alerts.id"))
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id"))       # area the appeal is for
    title: Mapped[str] = mapped_column(String(160))
    message: Mapped[str] = mapped_column(Text)
    target_province_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)      # who receives it
    category_ids: Mapped[list[int]] = mapped_column(JSONB, default=list)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
