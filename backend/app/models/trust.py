"""In-app notifications and rule-based fraud flags."""

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPk
from app.models._types import enum_col
from app.models.enums import FlagStatus, Severity


class Notification(UUIDPk, Timestamps, Base):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(40))       # e.g. donation_picked_up, appeal, rider_approved
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)   # e.g. {"donation_id": "..."} for deep links
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class FraudFlag(UUIDPk, Timestamps, Base):
    """A warning raised by a simple rule. Never proof: an admin reviews every flag."""

    __tablename__ = "fraud_flags"

    rule_code: Mapped[str] = mapped_column(String(40), index=True)   # e.g. far_from_ngo, same_photo, burst
    severity: Mapped[Severity] = mapped_column(enum_col(Severity))
    entity_type: Mapped[str] = mapped_column(String(20))             # user | donation | job
    entity_id: Mapped[uuid.UUID] = mapped_column(index=True)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[FlagStatus] = mapped_column(enum_col(FlagStatus), default=FlagStatus.open, index=True)
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    note: Mapped[Optional[str]] = mapped_column(Text)
