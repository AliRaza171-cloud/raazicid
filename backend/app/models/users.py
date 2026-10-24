"""Accounts: donors, riders, admins, plus rider verification."""

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPk
from app.models._types import enum_col
from app.models.enums import DocType, RiderStatus, Role, VehicleType


class User(UUIDPk, Timestamps, Base):
    __tablename__ = "users"

    role: Mapped[Role] = mapped_column(enum_col(Role), index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Home location: the most specific level the user picked (usually an area)
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("locations.id"), index=True)
    address: Mapped[Optional[str]] = mapped_column(Text)
    lat: Mapped[Optional[float]] = mapped_column(Float)
    lng: Mapped[Optional[float]] = mapped_column(Float)

    rider_profile: Mapped[Optional["RiderProfile"]] = relationship(
        back_populates="user", uselist=False, foreign_keys="RiderProfile.user_id"
    )


class RiderProfile(Timestamps, Base):
    """Extra data for users with role=rider. A rider cannot take jobs until status=approved."""

    __tablename__ = "rider_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    vehicle_type: Mapped[VehicleType] = mapped_column(enum_col(VehicleType))
    vehicle_number: Mapped[str] = mapped_column(String(20))
    status: Mapped[RiderStatus] = mapped_column(enum_col(RiderStatus), default=RiderStatus.pending, index=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=False)
    last_lat: Mapped[Optional[float]] = mapped_column(Float)
    last_lng: Mapped[Optional[float]] = mapped_column(Float)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    rating_avg: Mapped[Optional[float]] = mapped_column(Float)
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[Optional[str]] = mapped_column(Text)

    user: Mapped[User] = relationship(back_populates="rider_profile", foreign_keys=[user_id])
    documents: Mapped[list["RiderDocument"]] = relationship(back_populates="rider")


class RiderDocument(UUIDPk, Timestamps, Base):
    __tablename__ = "rider_documents"

    rider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rider_profiles.user_id", ondelete="CASCADE"), index=True)
    doc_type: Mapped[DocType] = mapped_column(enum_col(DocType))
    file_url: Mapped[str] = mapped_column(Text)   # Cloudinary URL

    rider: Mapped[RiderProfile] = relationship(back_populates="documents")


class DocumentReview(UUIDPk, Timestamps, Base):
    """AI (Claude) review of a rider's documents. Advisory only: the admin decides."""

    __tablename__ = "document_reviews"

    rider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rider_profiles.user_id", ondelete="CASCADE"), index=True)
    summary: Mapped[str] = mapped_column(Text)
    checks: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)   # [{"label", "ok", "detail"}]
    model: Mapped[str] = mapped_column(String(60))


class RefreshToken(UUIDPk, Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
