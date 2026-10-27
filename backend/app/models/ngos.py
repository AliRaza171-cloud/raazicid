"""NGOs that RAAZICID riders deliver donations to. Found by web search for a city, or added by an admin."""

import uuid
from typing import Optional

from sqlalchemy import Boolean, Column, Float, ForeignKey, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPk

# What each NGO takes (many-to-many). Empty = everything
ngo_categories = Table(
    "ngo_categories",
    Base.metadata,
    Column("ngo_id", ForeignKey("ngos.id", ondelete="CASCADE"), primary_key=True),
    Column("category_id", ForeignKey("categories.id"), primary_key=True),
)


class Ngo(UUIDPk, Timestamps, Base):
    """An NGO, charity or welfare trust with an office where our riders drop donations; it gives them out."""

    __tablename__ = "ngos"

    name: Mapped[str] = mapped_column(String(160))
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id"), index=True)   # its city or district
    address: Mapped[str] = mapped_column(Text)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    location_approx: Mapped[bool] = mapped_column(Boolean, default=False)   # city centre only: confirm before sending
    phone: Mapped[Optional[str]] = mapped_column(String(40))
    website: Mapped[Optional[str]] = mapped_column(Text)
    about: Mapped[Optional[str]] = mapped_column(Text)          # what they do, in a sentence
    takes_cooked_food: Mapped[bool] = mapped_column(Boolean, default=False)
    source_url: Mapped[Optional[str]] = mapped_column(Text)     # the web page it was found on
    found_by: Mapped[str] = mapped_column(String(20), default="admin")   # "web_search" or "admin"
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)       # an admin can hide one

    categories = relationship("Category", secondary=ngo_categories)
