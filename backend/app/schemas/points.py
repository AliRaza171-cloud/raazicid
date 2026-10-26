"""Shapes for distribution points and point requests."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.security import normalize_phone
from app.models.enums import PointType, RequestStatus
from app.schemas.donations import CategoryRef
from app.services.geo import in_pakistan


class _PointFields(BaseModel):
    @field_validator("name", "address", "contact_name", check_fields=False)
    @classmethod
    def tidy(cls, v: Optional[str]) -> Optional[str]:
        return " ".join(v.split()) if v else v

    @field_validator("contact_phone", check_fields=False)
    @classmethod
    def phone_ok(cls, v: Optional[str]) -> Optional[str]:
        return normalize_phone(v) if v else None

    @model_validator(mode="after")
    def coords(self):
        lat, lng = getattr(self, "lat", None), getattr(self, "lng", None)
        if (lat is None) != (lng is None):
            raise ValueError("Give both latitude and longitude")
        if lat is not None and not in_pakistan(lat, lng):
            raise ValueError("Coordinates must be in Pakistan (latitude first, e.g. 24.8607, 67.0011)")
        return self


class PointIn(_PointFields):
    name: str = Field(min_length=2, max_length=120)
    type: PointType
    location_id: uuid.UUID
    address: str = Field(min_length=3, max_length=500)
    lat: float
    lng: float
    contact_name: Optional[str] = Field(default=None, max_length=120)
    contact_phone: Optional[str] = None
    same_day_food: bool = False
    is_active: bool = True
    closes_at: Optional[datetime] = None
    category_ids: list[int] = Field(default_factory=list, description="Empty = accepts every category")
    allow_far: bool = Field(default=False, description="Save even if the coordinates are far from the chosen place")


class PointUpdate(_PointFields):
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    type: Optional[PointType] = None
    location_id: Optional[uuid.UUID] = None
    address: Optional[str] = Field(default=None, min_length=3, max_length=500)
    lat: Optional[float] = None
    lng: Optional[float] = None
    contact_name: Optional[str] = Field(default=None, max_length=120)
    contact_phone: Optional[str] = None
    same_day_food: Optional[bool] = None
    is_active: Optional[bool] = None
    closes_at: Optional[datetime] = None
    category_ids: Optional[list[int]] = None
    allow_far: bool = False


class PointRequestIn(BaseModel):
    category_id: int
    quantity: int = Field(ge=1, le=100000)
    note: Optional[str] = Field(default=None, max_length=500)


class PointRequestUpdate(BaseModel):
    status: RequestStatus


class PointRequestOut(BaseModel):
    id: uuid.UUID
    category: CategoryRef
    quantity: int
    note: Optional[str]
    status: RequestStatus
    requested_by_name: str
    created_at: datetime


class PointOut(BaseModel):
    id: uuid.UUID
    name: str
    type: PointType
    location_id: uuid.UUID
    location_path: list[str]
    address: str
    lat: float
    lng: float
    contact_name: Optional[str]
    contact_phone: Optional[str]
    same_day_food: bool
    is_active: bool
    closes_at: Optional[datetime]
    categories: list[CategoryRef]   # empty = accepts every category
    items_30d: int                  # donations sent here in the last 30 days
    open_requests: int
    created_at: datetime
    place_warning: Optional[str] = None   # coordinates far from the chosen place (wrong pin on the map)


class PointDetail(PointOut):
    requests: list[PointRequestOut]
