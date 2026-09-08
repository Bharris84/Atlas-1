"""Authentication and authorization.

Authentication is delegated to Supabase Auth. The API verifies the JWT
signature with the project's secret; it never sees or stores a password.

Development fallback
--------------------
With no ``SUPABASE_JWT_SECRET`` configured, the API runs as a fixed local user
so the app is usable with zero setup. That fallback is **refused in
production** — an unauthenticated production API would expose every user's
pipeline to anyone who found the URL.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings

logger = logging.getLogger("atlas.auth")

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    id: uuid.UUID
    email: Optional[str]
    is_development_identity: bool = False


class AuthConfigurationError(RuntimeError):
    """Raised at startup when production is missing its auth configuration."""


def verify_startup_configuration(settings: Settings) -> None:
    if settings.is_production and not settings.auth_configured:
        raise AuthConfigurationError(
            "SUPABASE_JWT_SECRET is required in production. Refusing to start with "
            "development authentication, which would leave the API open."
        )


def _decode(token: str, settings: Settings) -> dict:
    try:
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience=settings.supabase_jwt_audience,
            options={"require": ["sub", "exp"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired."
        ) from exc
    except jwt.InvalidTokenError as exc:
        # The specific reason is logged, never returned: telling a caller
        # exactly why a token failed helps them forge a better one.
        logger.warning("rejected token: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token."
        ) from exc


def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    if not settings.auth_configured:
        # Development mode. Guarded at startup so it cannot happen in prod.
        return CurrentUser(
            id=uuid.UUID(settings.dev_user_id),
            email=settings.dev_user_email,
            is_development_identity=True,
        )

    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = _decode(credentials.credentials, settings)
    subject = payload.get("sub")
    try:
        user_id = uuid.UUID(str(subject))
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token subject is not a valid user id.",
        ) from exc

    return CurrentUser(id=user_id, email=payload.get("email"))
