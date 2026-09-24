from __future__ import annotations

from types import SimpleNamespace
import time

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import config
import services.auth as auth
from config import Settings
from modules.chat.router import router as chat_router


def test_chat_history_rejects_missing_bearer_before_database_access() -> None:
    app = FastAPI()
    app.include_router(chat_router)
    with TestClient(app) as client:
        response = client.get("/chat/sessions?user_id=owner-a")
    assert response.status_code == 401


def test_hs256_test_token_is_limited_to_development(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "test-jwt-secret-that-is-long-enough-for-hs256"
    token = jwt.encode({"sub": "owner-a"}, secret, algorithm="HS256")

    monkeypatch.setattr(
        config,
        "settings",
        Settings(app_environment="development", jwt_secret=secret),
    )
    assert auth.decode_identity_token(token).user_id == "owner-a"

    monkeypatch.setattr(
        config,
        "settings",
        Settings(app_environment="production", jwt_secret=secret),
    )
    with pytest.raises(auth.AuthenticationError, match="UNSUPPORTED_ID_TOKEN"):
        auth.decode_identity_token(token)


def test_firebase_rs256_contract_validates_audience_and_issuer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cryptography.hazmat.primitives.asymmetric import rsa as cryptography
    private_key = cryptography.generate_private_key(public_exponent=65537, key_size=2048)
    project_id = "firebase-project-test"
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": "firebase-owner",
            "aud": project_id,
            "iss": f"https://securetoken.google.com/{project_id}",
            "iat": now,
            "auth_time": now - 1,
            "exp": now + 3600,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )
    monkeypatch.setattr(
        config,
        "settings",
        Settings(app_environment="production", firebase_project_id=project_id),
    )
    monkeypatch.setattr(
        auth,
        "_firebase_jwk_client",
        lambda _project: SimpleNamespace(
            get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=private_key.public_key())
        ),
    )

    assert auth.decode_identity_token(token).user_id == "firebase-owner"


def test_firebase_rs256_rejects_future_authentication_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cryptography.hazmat.primitives.asymmetric import rsa as cryptography
    private_key = cryptography.generate_private_key(public_exponent=65537, key_size=2048)
    project_id = "firebase-project-test"
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": "firebase-owner",
            "aud": project_id,
            "iss": f"https://securetoken.google.com/{project_id}",
            "iat": now,
            "auth_time": now + 3600,
            "exp": now + 3600,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )
    monkeypatch.setattr(
        config,
        "settings",
        Settings(app_environment="production", firebase_project_id=project_id),
    )
    monkeypatch.setattr(
        auth,
        "_firebase_jwk_client",
        lambda _project: SimpleNamespace(
            get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=private_key.public_key())
        ),
    )

    with pytest.raises(auth.AuthenticationError, match="INVALID_ID_TOKEN_AUTH_TIME"):
        auth.decode_identity_token(token)


def test_firebase_rs256_allows_small_clock_skew(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cryptography.hazmat.primitives.asymmetric import rsa as cryptography

    private_key = cryptography.generate_private_key(public_exponent=65537, key_size=2048)
    project_id = "firebase-project-test"
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": "firebase-owner", "aud": project_id,
            "iss": f"https://securetoken.google.com/{project_id}",
            "iat": now, "auth_time": now + 30, "exp": now + 3600,
        },
        private_key, algorithm="RS256", headers={"kid": "test-key"},
    )
    monkeypatch.setattr(
        config, "settings", Settings(app_environment="production", firebase_project_id=project_id)
    )
    monkeypatch.setattr(
        auth, "_firebase_jwk_client",
        lambda _project: SimpleNamespace(
            get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=private_key.public_key())
        ),
    )

    assert auth.decode_identity_token(token).user_id == "firebase-owner"
