"""Shapes for the admin rider verification pages."""

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from app.models.enums import RiderStatus, VehicleType
from app.schemas.auth import RiderDocOut


class RiderListItem(BaseModel):
    id: uuid.UUID
    full_name: str
    phone: str
    vehicle_type: VehicleType
    vehicle_number: str
    status: RiderStatus
    location_path: list[str]
    documents_count: int
    created_at: datetime


class RiderList(BaseModel):
    items: list[RiderListItem]
    total: int


class RiderDetail(RiderListItem):
    email: Optional[str]
    review_note: Optional[str]
    reviewed_at: Optional[datetime]
    documents: list[RiderDocOut]


class RiderCounts(BaseModel):
    pending: int
    approved: int
    rejected: int
    suspended: int


class DecisionIn(BaseModel):
    action: Literal["approve", "reject", "suspend", "request_document"]
    note: Optional[str] = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def note_needed(self) -> "DecisionIn":
        if self.action in ("reject", "request_document", "suspend") and not (self.note or "").strip():
            raise ValueError("Write a short note so the rider knows why")
        return self
