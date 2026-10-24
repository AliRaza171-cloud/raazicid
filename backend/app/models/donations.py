"""Donations, their photos, status history, hand-outs and ratings."""

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPk
from app.models._types import enum_col
from app.models.enums import Condition, DonationStatus, FoodType, ImageKind


class Donation(UUIDPk, Timestamps, Base):
    __tablename__ = "donations"

    donor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)   # final, confirmed by donor

    # AI suggestion from the image classifier (advisory)
    ai_category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"))
    ai_confidence: Mapped[Optional[float]] = mapped_column(Float)
    ai_top3: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSONB)   # [{"category": "blankets", "p": 0.92}, ...]

    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[Optional[str]] = mapped_column(Text)
    quantity: Mapped[int] = mapped_column(Integer)
    condition: Mapped[Optional[Condition]] = mapped_column(enum_col(Condition))

    is_food: Mapped[bool] = mapped_column(default=False)
    food_type: Mapped[Optional[FoodType]] = mapped_column(enum_col(FoodType))
    prepared_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    urgency_score: Mapped[Optional[int]] = mapped_column(SmallInteger, index=True)   # 0-100, rule-based

    pickup_address: Mapped[str] = mapped_column(Text)
    pickup_lat: Mapped[float] = mapped_column(Float)
    pickup_lng: Mapped[float] = mapped_column(Float)
    pickup_location_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("locations.id"), index=True)
    pickup_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    pickup_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    status: Mapped[DonationStatus] = mapped_column(
        enum_col(DonationStatus), default=DonationStatus.in_review, index=True
    )
    reject_reason: Mapped[Optional[str]] = mapped_column(Text)
    point_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("distribution_points.id"), index=True)
    appeal_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("appeals.id"))   # donated in answer to an appeal

    images: Mapped[list["DonationImage"]] = relationship(back_populates="donation", cascade="all, delete-orphan")
    history: Mapped[list["StatusChange"]] = relationship(
        back_populates="donation", cascade="all, delete-orphan", order_by="StatusChange.created_at"
    )
    jobs = relationship("Job", back_populates="donation", cascade="all, delete-orphan")


class DonationImage(UUIDPk, Timestamps, Base):
    __tablename__ = "donation_images"

    donation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("donations.id", ondelete="CASCADE"), index=True)
    kind: Mapped[ImageKind] = mapped_column(enum_col(ImageKind))
    url: Mapped[str] = mapped_column(Text)   # Cloudinary URL
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    lat: Mapped[Optional[float]] = mapped_column(Float)   # where proof photos were taken
    lng: Mapped[Optional[float]] = mapped_column(Float)

    donation: Mapped[Donation] = relationship(back_populates="images")


class StatusChange(UUIDPk, Timestamps, Base):
    """Every status move, who made it and when. Used for the timeline and for audits."""

    __tablename__ = "status_changes"

    donation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("donations.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[Optional[DonationStatus]] = mapped_column(enum_col(DonationStatus))
    to_status: Mapped[DonationStatus] = mapped_column(enum_col(DonationStatus))
    changed_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"))   # null = system
    note: Mapped[Optional[str]] = mapped_column(Text)

    donation: Mapped[Donation] = relationship(back_populates="history")


class HandOut(UUIDPk, Timestamps, Base):
    """Our team handing items to families at a point (the final step)."""

    __tablename__ = "hand_outs"

    donation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("donations.id", ondelete="CASCADE"), index=True)
    point_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("distribution_points.id"), index=True)
    handed_out_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))   # rider or admin
    quantity: Mapped[int] = mapped_column(Integer)
    families_served: Mapped[Optional[int]] = mapped_column(Integer)
    photo_url: Mapped[Optional[str]] = mapped_column(Text)
    note: Mapped[Optional[str]] = mapped_column(Text)


class Rating(UUIDPk, Timestamps, Base):
    __tablename__ = "ratings"

    donation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("donations.id", ondelete="CASCADE"), index=True)
    rater_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    rider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    score: Mapped[int] = mapped_column(SmallInteger)   # 1-5
    comment: Mapped[Optional[str]] = mapped_column(Text)
