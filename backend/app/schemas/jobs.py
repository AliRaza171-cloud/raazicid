"""Shapes for rider jobs, proof photos and live tracking (Phase 4)."""

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import FoodType, JobStatus, VehicleType
from app.services.geo import in_pakistan


def _https(v: Optional[str]) -> Optional[str]:
    if v is not None and (not v.startswith("https://") or len(v) > 1000):
        raise ValueError("Upload the photo first (https link)")
    return v


class _Coords(BaseModel):
    lat: float
    lng: float

    @model_validator(mode="after")
    def in_pk(self):
        if not in_pakistan(self.lat, self.lng):
            raise ValueError("Your location looks wrong. Turn on GPS and try again")
        return self


# ---------- admin ----------

class ScoreReason(BaseModel):
    label: str
    points: int


class RiderOption(BaseModel):
    id: uuid.UUID
    full_name: str
    phone: str
    vehicle_type: VehicleType
    vehicle_number: str
    is_available: bool
    active_jobs: int
    match: Literal["same_area", "same_region", "same_city", "same_province", "other"]
    distance_km: Optional[float]      # from the rider's last GPS position (if seen in the last 2 hours)
    last_seen_at: Optional[datetime]
    rating_avg: Optional[float]
    score: int                         # 0-100, see app/services/recommend.py
    reasons: list[ScoreReason]


class AssignIn(BaseModel):
    rider_id: uuid.UUID


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


# ---------- rider ----------

class AvailabilityIn(BaseModel):
    is_available: bool


class RiderSummary(BaseModel):
    is_available: bool
    active_jobs: int
    done_today: int
    done_total: int
    rating_avg: Optional[float]


class ProofIn(_Coords):
    photo_url: str
    note: Optional[str] = Field(default=None, max_length=500)

    @field_validator("photo_url")
    @classmethod
    def url_ok(cls, v: str) -> str:
        return _https(v)


class PingIn(_Coords):
    pass


class Place(BaseModel):
    name: Optional[str] = None
    address: str
    lat: float
    lng: float
    area: list[str]
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    approx: bool = False               # only the city centre is known: call the NGO for directions


class JobOut(BaseModel):
    id: uuid.UUID
    status: JobStatus
    assigned_at: datetime
    accepted_at: Optional[datetime]
    picked_up_at: Optional[datetime]
    delivered_at: Optional[datetime]
    decline_reason: Optional[str]
    donation_id: uuid.UUID
    donation_ref: str
    donation_status: str
    title: str
    category: str
    quantity: int
    description: Optional[str]
    is_food: bool
    food_type: Optional[FoodType]
    prepared_at: Optional[datetime]
    urgency_score: Optional[int]
    photos: list[str]
    pickup: Place
    pickup_from: Optional[datetime]
    pickup_to: Optional[datetime]
    ngo: Optional[Place]                # where to drop it
    donor_name: str
    donor_phone: Optional[str]          # shown once the rider has accepted the job
    trip_km: Optional[float]            # pickup -> NGO, straight line


class JobList(BaseModel):
    items: list[JobOut]
    total: int


# ---------- tracking ----------

class LatLng(BaseModel):
    lat: float
    lng: float
    at: datetime


class TrackingRider(BaseModel):
    full_name: str
    phone: str
    vehicle_type: VehicleType
    vehicle_number: str


class TrackingOut(BaseModel):
    donation_id: uuid.UUID
    donation_status: str
    job_id: Optional[uuid.UUID]
    job_status: Optional[JobStatus]
    heading_to: Optional[Literal["pickup", "ngo"]]
    rider: Optional[TrackingRider]
    last: Optional[LatLng]
    path: list[LatLng]
    stalled: bool                      # no GPS for 10+ minutes during an active job
    pickup: Place
    ngo: Optional[Place]


class AdminTrackingItem(BaseModel):
    job_id: uuid.UUID
    job_status: JobStatus
    donation_id: uuid.UUID
    donation_ref: str
    title: str
    rider_name: str
    rider_phone: str
    heading_to: Literal["pickup", "ngo"]
    last: Optional[LatLng]
    minutes_since_ping: Optional[int]
    stalled: bool
    pickup: Place
    ngo: Optional[Place]
