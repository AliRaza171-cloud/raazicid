"""Places (province > city > region > area) and the 12 donation categories."""

import uuid
from typing import Optional

from sqlalchemy import Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPk
from app.models._types import enum_col
from app.models.enums import LocationLevel


class Location(UUIDPk, Base):
    """One row per place. `parent_id` builds the tree: Sindh > Karachi > Karachi South > Lyari."""

    __tablename__ = "locations"
    __table_args__ = (UniqueConstraint("parent_id", "name", name="uq_location_parent_name"),)

    name: Mapped[str] = mapped_column(String(120))
    level: Mapped[LocationLevel] = mapped_column(enum_col(LocationLevel), index=True)
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("locations.id"), index=True)
    # Official codes (e.g. HDX admin1/admin2 codes) so outside data can be matched to our places
    admin_code: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    lat: Mapped[Optional[float]] = mapped_column(Float)
    lng: Mapped[Optional[float]] = mapped_column(Float)

    parent: Mapped[Optional["Location"]] = relationship(remote_side="Location.id", back_populates="children")
    children: Mapped[list["Location"]] = relationship(back_populates="parent")


class Category(Base):
    """The 12 donation categories (seeded, rarely change)."""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(60))
    is_perishable: Mapped[bool] = mapped_column(default=False)
