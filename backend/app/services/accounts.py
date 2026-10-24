"""Shared account logic used by several routes."""

from sqlalchemy.orm import Session

from app.core.security import create_access_token, new_refresh_token
from app.models import Notification, RefreshToken, User
from app.schemas.auth import TokenOut, UserOut
from app.services.locations import location_path


def user_out(db: Session, user: User) -> UserOut:
    rp = user.rider_profile
    return UserOut(
        id=user.id,
        role=user.role,
        full_name=user.full_name,
        phone=user.phone,
        email=user.email,
        location_id=user.location_id,
        location_path=location_path(db, user.location_id),
        address=user.address,
        rider_status=rp.status if rp else None,
        rider_note=rp.review_note if rp else None,
        created_at=user.created_at,
    )


def issue_tokens(db: Session, user: User) -> TokenOut:
    """New access token + new refresh token (stored hashed). Commits."""
    raw, token_hash, expires = new_refresh_token()
    db.add(RefreshToken(user_id=user.id, token_hash=token_hash, expires_at=expires))
    db.commit()
    db.refresh(user)
    return TokenOut(
        user=user_out(db, user),
        access_token=create_access_token(user.id, user.role.value),
        refresh_token=raw,
    )


def notify(db: Session, user: User, type_: str, title: str, body: str, data: dict | None = None) -> None:
    """Add an in-app notification (caller commits)."""
    db.add(Notification(user_id=user.id, type=type_, title=title, body=body, data=data or {}))
