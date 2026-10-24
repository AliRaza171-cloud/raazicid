"""Request and response shapes for accounts (see docs/api-contract.md)."""

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.core.security import normalize_phone
from app.models.enums import DocType, RiderStatus, Role, VehicleType


class RiderIn(BaseModel):
    vehicle_type: VehicleType
    vehicle_number: str = Field(min_length=2, max_length=20)

    @field_validator("vehicle_number")
    @classmethod
    def upper(cls, v: str) -> str:
        return v.strip().upper()


class RegisterIn(BaseModel):
    role: Literal["donor", "rider"]   # admins are created with app.seed.create_admin, never by sign-up
    full_name: str = Field(min_length=2, max_length=120)
    phone: str
    email: Optional[EmailStr] = None
    password: str = Field(min_length=8, max_length=72)   # bcrypt reads at most 72 bytes
    location_id: Optional[uuid.UUID] = None
    address: Optional[str] = Field(default=None, max_length=500)
    rider: Optional[RiderIn] = None

    @field_validator("phone")
    @classmethod
    def phone_ok(cls, v: str) -> str:
        return normalize_phone(v)

    @field_validator("full_name")
    @classmethod
    def name_ok(cls, v: str) -> str:
        return " ".join(v.split())

    @model_validator(mode="after")
    def rider_details(self) -> "RegisterIn":
        if self.role == "rider" and self.rider is None:
            raise ValueError("Riders must give their vehicle type and number")
        if self.role == "donor":
            self.rider = None
        return self


class LoginIn(BaseModel):
    login: str = Field(min_length=3, description="Phone number or email")
    password: str = Field(min_length=1, max_length=72)


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=10)


class UserOut(BaseModel):
    id: uuid.UUID
    role: Role
    full_name: str
    phone: str
    email: Optional[str]
    location_id: Optional[uuid.UUID]
    location_path: list[str]          # e.g. ["Sindh", "Karachi", "Karachi East", "Gulshan-e-Iqbal"]
    address: Optional[str]
    rider_status: Optional[RiderStatus] = None
    rider_note: Optional[str] = None  # admin's note, e.g. which document to re-upload
    created_at: datetime


class TokenOut(BaseModel):
    user: UserOut
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class MeUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    email: Optional[EmailStr] = None
    location_id: Optional[uuid.UUID] = None
    address: Optional[str] = Field(default=None, max_length=500)
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)


class RiderDocIn(BaseModel):
    doc_type: DocType
    file_url: str = Field(min_length=10, max_length=1000)

    @field_validator("file_url")
    @classmethod
    def https_only(cls, v: str) -> str:
        if not v.startswith("https://"):
            raise ValueError("Upload the file first; file_url must be an https link")
        return v


class RiderDocOut(BaseModel):
    id: uuid.UUID
    doc_type: DocType
    file_url: str
    created_at: datetime


class UploadSignIn(BaseModel):
    purpose: Literal["rider_document", "donation_photo", "proof_photo"]


class UploadSignOut(BaseModel):
    """Everything the app needs to upload one file straight to Cloudinary."""
    upload_url: str
    cloud_name: str
    api_key: str
    timestamp: int
    folder: str
    signature: str
