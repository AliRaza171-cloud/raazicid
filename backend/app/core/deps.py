"""Who is calling? FastAPI dependencies for logged-in users and roles."""

import uuid
from collections.abc import Callable

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import api_error
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import User
from app.models.enums import Role

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise api_error(401, "not_authenticated", "Please log in")
    try:
        payload = decode_access_token(creds.credentials)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise api_error(401, "invalid_token", "Your session has expired. Please log in again")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise api_error(401, "invalid_token", "Your session has expired. Please log in again")
    return user


def require_roles(*roles: Role) -> Callable[..., User]:
    """Use as: user: User = Depends(require_roles(Role.admin))"""

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise api_error(403, "forbidden", "You do not have access to this")
        return user

    return checker
