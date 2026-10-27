"""Shapes for NGOs (where our riders drop donations)."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.donations import CategoryRef
from app.services.geo import in_pakistan


class _NgoFields(BaseModel):
    @field_validator("name", "address", "phone", "about", check_fields=False)
    @classmethod
    def tidy(cls, v: Optional[str]) -> Optional[str]:
        return " ".join(v.split()) if v else v

    @field_validator("website", check_fields=False)
    @classmethod
    def web(cls, v: Optional[str]) -> Optional[str]:
        if not v or not v.strip():
            return None
        v = v.strip()
        return v if v.startswith(("http://", "https://")) else "https://" + v

    @model_validator(mode="after")
    def coords(self):
        lat, lng = getattr(self, "lat", None), getattr(self, "lng", None)
        if (lat is None) != (lng is None):
            raise ValueError("Give both latitude and longitude")
        if lat is not None and not in_pakistan(lat, lng):
            raise ValueError("Coordinates must be in Pakistan (latitude first, e.g. 25.3960, 68.3578)")
        return self


class NgoIn(_NgoFields):
    name: str = Field(min_length=2, max_length=160)
    location_id: uuid.UUID
    address: str = Field(min_length=3, max_length=500)
    lat: float
    lng: float
    phone: Optional[str] = Field(default=None, max_length=40)
    website: Optional[str] = Field(default=None, max_length=300)
    about: Optional[str] = Field(default=None, max_length=1000)
    takes_cooked_food: bool = False
    category_ids: list[int] = Field(default_factory=list, description="Empty = takes every category")


class NgoUpdate(_NgoFields):
    name: Optional[str] = Field(default=None, min_length=2, max_length=160)
    location_id: Optional[uuid.UUID] = None
    address: Optional[str] = Field(default=None, min_length=3, max_length=500)
    lat: Optional[float] = None
    lng: Optional[float] = None
    phone: Optional[str] = Field(default=None, max_length=40)
    website: Optional[str] = Field(default=None, max_length=300)
    about: Optional[str] = Field(default=None, max_length=1000)
    takes_cooked_food: Optional[bool] = None
    is_active: Optional[bool] = None
    category_ids: Optional[list[int]] = None


class NgoOut(BaseModel):
    id: uuid.UUID
    name: str
    location_id: uuid.UUID
    location_path: list[str]
    address: str
    lat: float
    lng: float
    location_approx: bool
    phone: Optional[str]
    website: Optional[str]
    about: Optional[str]
    takes_cooked_food: bool
    source_url: Optional[str]
    found_by: str
    is_active: bool
    categories: list[CategoryRef]   # empty = takes everything
    items_30d: int                  # donations sent here in the last 30 days
    created_at: datetime
    place_warning: Optional[str] = None   # the pin is far from its city (wrong address found?)


class NgoSearchIn(BaseModel):
    location_id: uuid.UUID          # a city or district (a smaller place searches its city)
    category_id: Optional[int] = None


class NgoSearchOut(BaseModel):
    place: str
    found: int
    added: int
    updated: int
    status: str
    ngos: list[NgoOut]
