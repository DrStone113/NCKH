"""Shared authentication and owner identity for HTTP and WebSocket routes."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from fastapi import Header, HTTPException
from jwt import PyJWKClient

import config


_FIREBASE_CLOCK_SKEW_SECONDS = 60
_FIREBASE_JWK_ATTEMPTS = 2


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    user_id: str
    roles: frozenset[str] = frozenset()

    @property
    def is_developer(self) -> bool:
        return bool(self.roles.intersection({"admin", "developer"}))


class AuthenticationError(ValueError):
    pass


@lru_cache(maxsize=2)
def _firebase_jwk_client(project_id: str) -> PyJWKClient:
    del project_id
    return PyJWKClient(
        "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com",
        cache_keys=True,
        timeout=5,
    )


def _roles(payload: dict[str, Any]) -> frozenset[str]:
    raw = payload.get("roles") or payload.get("role") or []
    values = [raw] if isinstance(raw, str) else raw if isinstance(raw, list) else []
    roles = {str(value).strip().lower() for value in values if str(value).strip()}
    if payload.get("admin") or payload.get("is_admin"):
        roles.add("admin")
    if payload.get("developer") or payload.get("is_developer"):
        roles.add("developer")
    return frozenset(roles)


def _firebase_signing_key(project_id: str, token: str) -> Any:
    """Fetch the rotating Firebase signing key with one bounded transient retry."""

    client = _firebase_jwk_client(project_id)
    error: Exception | None = None
    for attempt in range(_FIREBASE_JWK_ATTEMPTS):
        try:
            return client.get_signing_key_from_jwt(token).key
        except (jwt.PyJWTError, OSError, ValueError) as exc:
            error = exc
            if attempt + 1 < _FIREBASE_JWK_ATTEMPTS:
                time.sleep(0.1)
    assert error is not None
    raise error


def decode_identity_token(token: str) -> AuthenticatedPrincipal:
    """Verify a Firebase token, with local HS256 tokens limited to dev/test."""

    try:
        header = jwt.get_unverified_header(token)
        algorithm = str(header.get("alg") or "")
        if algorithm == "RS256":
            if not str(header.get("kid") or "").strip():
                raise AuthenticationError("INVALID_ID_TOKEN_KEY_ID")
            project_id = config.settings.firebase_project_id.strip()
            if not project_id:
                raise AuthenticationError("FIREBASE_PROJECT_ID_NOT_CONFIGURED")
            signing_key = _firebase_signing_key(project_id, token)
            payload = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                audience=project_id,
                issuer=f"https://securetoken.google.com/{project_id}",
                leeway=_FIREBASE_CLOCK_SKEW_SECONDS,
                options={
                    "require": ["exp", "iat", "auth_time", "sub", "aud", "iss"]
                },
            )
        elif algorithm == "HS256" and config.settings.app_environment.strip().lower() in {
            "development",
            "test",
        }:
            payload = jwt.decode(token, config.settings.jwt_secret, algorithms=["HS256"])
        else:
            raise AuthenticationError("UNSUPPORTED_ID_TOKEN")
    except AuthenticationError:
        raise
    except (jwt.PyJWTError, OSError, ValueError) as exc:
        raise AuthenticationError("INVALID_ID_TOKEN") from exc

    user_id = payload.get("sub")
    if (
        not isinstance(user_id, str)
        or not user_id.strip()
        or len(user_id) > 128
        or user_id == "anonymous"
    ):
        raise AuthenticationError("INVALID_ID_TOKEN_SUBJECT")
    if algorithm == "RS256":
        auth_time = payload.get("auth_time")
        if (
            not isinstance(auth_time, (int, float))
            or auth_time > time.time() + _FIREBASE_CLOCK_SKEW_SECONDS
        ):
            raise AuthenticationError("INVALID_ID_TOKEN_AUTH_TIME")
    return AuthenticatedPrincipal(user_id.strip(), _roles(payload))


async def authenticate_token(token: str) -> AuthenticatedPrincipal:
    return await asyncio.to_thread(decode_identity_token, token)


def bearer_token(authorization: str | None) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthenticationError("AUTHENTICATED_PRINCIPAL_REQUIRED")
    return token.strip()


async def require_authenticated_principal(
    authorization: str | None = Header(default=None),
) -> AuthenticatedPrincipal:
    try:
        return await authenticate_token(bearer_token(authorization))
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def require_owner(principal: AuthenticatedPrincipal, claimed_user_id: str) -> None:
    if claimed_user_id != principal.user_id:
        raise HTTPException(status_code=403, detail="OWNER_MISMATCH")


__all__ = [
    "AuthenticatedPrincipal",
    "AuthenticationError",
    "authenticate_token",
    "bearer_token",
    "decode_identity_token",
    "require_authenticated_principal",
    "require_owner",
]
