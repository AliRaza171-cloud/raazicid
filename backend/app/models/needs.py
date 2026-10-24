"""Need data: raw indicators, the computed need level per area and category, and seasonal rules."""

import uuid
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, SmallInteger, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPk


class NeedIndicator(UUIDPk, Timestamps, Base):
    """One number about one place, e.g. 'share of people in IPC Phase 3+ in Kech = 0.34'.

    `indicator` examples: ipc_phase3plus_share, price_change_3m, poverty_headcount,
    open_point_requests, delivered_30d.
    """

    __tablename__ = "need_indicators"

    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id"), index=True)
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"), index=True)  # null = applies to all
    indicator: Mapped[str] = mapped_column(String(60), index=True)
    value: Mapped[float] = mapped_column(Float)
    period_start: Mapped[Optional[date]] = mapped_column(Date)
    period_end: Mapped[Optional[date]] = mapped_column(Date, index=True)
    source_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sources.id"))
    report_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("reports.id"))
    meta: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)   # e.g. {"market": "Central Karachi", "commodity": "Wheat flour"}


class NeedLevel(Base):
    """What the 'Needs by area' page shows: one level per area and category, recomputed on a schedule."""

    __tablename__ = "need_levels"
    __table_args__ = (UniqueConstraint("location_id", "category_id", name="uq_need_level_loc_cat"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    level: Mapped[int] = mapped_column(SmallInteger)      # 0 none, 1 some, 2 high, 3 urgent
    score: Mapped[float] = mapped_column(Float)           # 0-100 before banding
    # [{"why": "IPC Phase 3+ for 34% of people", "sources": ["IPC food insecurity"]}]
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SeasonalRule(UUIDPk, Timestamps, Base):
    """E.g. 'Winter: Dec-Feb, blankets, weight 3, KP x1.5'. Hijri events move every year."""

    __tablename__ = "seasonal_rules"

    name: Mapped[str] = mapped_column(String(80))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    start_month: Mapped[Optional[int]] = mapped_column(SmallInteger)   # 1-12, Gregorian
    end_month: Mapped[Optional[int]] = mapped_column(SmallInteger)
    hijri_month: Mapped[Optional[int]] = mapped_column(SmallInteger)   # e.g. 9 = Ramadan
    days_before_event: Mapped[Optional[int]] = mapped_column(Integer)  # e.g. 14 days before Eid
    province_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("locations.id"))  # null = all Pakistan
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
