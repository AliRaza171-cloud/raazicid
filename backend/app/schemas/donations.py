"""Shapes for donations (donor app and admin). See docs/api-contract.md."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import Condition, DonationStatus, FoodType
from app.services.geo import in_pakistan


class AiSuggestion(BaseModel):
    """Filled by the on-phone/server classifier from Phase 5. Optional until then."""
    category_id: int
    confidence: float = Field(ge=0, le=1)
    top3: list[dict] = Field(default_factory=list, max_length=3)


class PickupIn(BaseModel):
    address: str = Field(min_length=5, max_length=500)
    lat: float
    lng: float
    location_id: uuid.UUID
    from_: datetime = Field(alias="from")
    to: datetime

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def check(self) -> "PickupIn":
        if not in_pakistan(self.lat, self.lng):
            raise ValueError("Pickup location must be in Pakistan. Tap 'Use my current location' again")
        start, end = _aware(self.from_), _aware(self.to)
        now = datetime.now(timezone.utc)
        if end <= start:
            raise ValueError("Pickup time must end after it starts")
        if end <= now:
            raise ValueError("Pickup time is already over. Choose a later time")
        if start > now + timedelta(days=7):
            raise ValueError("Choose a pickup time within the next 7 days")
        self.from_, self.to = start, end
        return self


def _aware(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


class DonationIn(BaseModel):
    category_id: int
    ai: Optional[AiSuggestion] = None
    title: str = Field(min_length=2, max_length=160)
    quantity: int = Field(ge=1, le=10000)
    condition: Optional[Condition] = None
    description: Optional[str] = Field(default=None, max_length=1000)
    is_food: bool = False
    food_type: Optional[FoodType] = None
    prepared_at: Optional[datetime] = None
    pickup: PickupIn
    photo_urls: list[str] = Field(min_length=1, max_length=5)

    @field_validator("title")
    @classmethod
    def tidy(cls, v: str) -> str:
        return " ".join(v.split())

    @field_validator("photo_urls")
    @classmethod
    def https_only(cls, v: list[str]) -> list[str]:
        if any(not u.startswith("https://") or len(u) > 1000 for u in v):
            raise ValueError("Photos must be uploaded first (https links)")
        return v

    @model_validator(mode="after")
    def food_rules(self) -> "DonationIn":
        if self.is_food:
            if self.food_type is None:
                raise ValueError("Say whether the food is cooked or dry / packed")
            if self.food_type == FoodType.cooked:
                if self.prepared_at is None:
                    raise ValueError("Say when the cooked food was prepared")
                self.prepared_at = _aware(self.prepared_at)
                if self.prepared_at > datetime.now(timezone.utc) + timedelta(minutes=10):
                    raise ValueError("Prepared time cannot be in the future")
            else:
                self.prepared_at = None
        else:
            self.food_type = None
            self.prepared_at = None
        return self


class CategoryRef(BaseModel):
    id: int
    name: str


class PointRef(BaseModel):
    id: uuid.UUID
    name: str
    address: str
    location_path: list[str]


class HistoryItem(BaseModel):
    from_status: Optional[DonationStatus]
    to_status: DonationStatus
    note: Optional[str]
    by_name: Optional[str]   # None = system
    at: datetime


class DonorRef(BaseModel):
    id: uuid.UUID
    full_name: str
    phone: str
    donations_count: int


class UrgencyReason(BaseModel):
    label: str
    points: int


class DonationListItem(BaseModel):
    id: uuid.UUID
    ref: str                       # short id shown to people, e.g. D-3F9A1C
    title: str
    category: CategoryRef
    quantity: int
    status: DonationStatus
    is_food: bool
    urgency_score: Optional[int]
    photo_url: Optional[str]
    pickup_area: list[str]         # last two place names, e.g. ["Karachi East", "Gulshan-e-Iqbal"]
    point_name: Optional[str]
    donor_name: Optional[str] = None   # admin list only
    created_at: datetime


class DonationList(BaseModel):
    items: list[DonationListItem]
    total: int


class Pickup(BaseModel):
    address: str
    lat: float
    lng: float
    location_id: Optional[uuid.UUID]
    location_path: list[str]
    from_: Optional[datetime] = Field(serialization_alias="from")
    to: Optional[datetime]


class DonationOut(DonationListItem):
    description: Optional[str]
    condition: Optional[Condition]
    food_type: Optional[FoodType]
    prepared_at: Optional[datetime]
    urgency_reasons: list[UrgencyReason]
    pickup: Pickup
    point: Optional[PointRef]
    reject_reason: Optional[str]
    photos: list[str]
    history: list[HistoryItem]
    donor: DonorRef
    ai: Optional[AiSuggestion]
    can_cancel: bool


class DonationCounts(BaseModel):
    in_review: int
    accepted: int
    rejected: int
    rider_assigned: int
    picked_up: int
    at_point: int
    handed_out: int
    cancelled: int


class AcceptIn(BaseModel):
    point_id: uuid.UUID


class RejectIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class PointOption(BaseModel):
    """A distribution point that can take this donation, ranked for the admin."""
    id: uuid.UUID
    name: str
    type: str
    location_path: list[str]
    distance_km: float
    match: Literal["same_area", "same_region", "same_city", "same_province", "other"]
    same_day_food: bool
    items_30d: int
