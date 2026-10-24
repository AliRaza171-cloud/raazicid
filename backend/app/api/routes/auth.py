"""Sign-up, login, token refresh and logout."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import api_error
from app.core.security import hash_password, hash_refresh_token, looks_like_phone, normalize_phone, verify_password
from app.db.session import get_db
from app.models import Location, RefreshToken, RiderProfile, User
from app.models.enums import RiderStatus, Role
from app.schemas.auth import LoginIn, RefreshIn, RegisterIn, TokenOut
from app.services.accounts import issue_tokens

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.phone == body.phone)):
        raise api_error(409, "phone_taken", "An account with this phone number already exists")
    email = body.email.lower() if body.email else None
    if email and db.scalar(select(User).where(func.lower(User.email) == email)):
        raise api_error(409, "email_taken", "An account with this email already exists")
    if body.location_id and db.get(Location, body.location_id) is None:
        raise api_error(422, "bad_location", "Choose your area from the list")

    user = User(
        role=Role(body.role),
        full_name=body.full_name,
        phone=body.phone,
        email=email,
        password_hash=hash_password(body.password),
        location_id=body.location_id,
        address=body.address,
    )
    db.add(user)
    db.flush()
    if body.rider:
        db.add(RiderProfile(
            user_id=user.id,
            vehicle_type=body.rider.vehicle_type,
            vehicle_number=body.rider.vehicle_number,
            status=RiderStatus.pending,
        ))
    return issue_tokens(db, user)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    if looks_like_phone(body.login):
        user = db.scalar(select(User).where(User.phone == normalize_phone(body.login)))
    else:
        user = db.scalar(select(User).where(func.lower(User.email) == body.login.strip().lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise api_error(401, "wrong_login", "Phone/email or password is wrong")
    if not user.is_active:
        raise api_error(403, "account_disabled", "This account has been disabled. Contact RAAZICID")
    return issue_tokens(db, user)


@router.post("/refresh", response_model=TokenOut)
def refresh(body: RefreshIn, db: Session = Depends(get_db)):
    """Swap a refresh token for a new pair. The old refresh token stops working (rotation)."""
    now = datetime.now(timezone.utc)
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(body.refresh_token)))
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        raise api_error(401, "invalid_refresh", "Your session has expired. Please log in again")
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise api_error(401, "invalid_refresh", "Your session has expired. Please log in again")
    row.revoked_at = now
    return issue_tokens(db, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(body: RefreshIn, db: Session = Depends(get_db)):
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(body.refresh_token)))
    if row is not None and row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
        db.commit()
