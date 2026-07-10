from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from jose import jwt

from app.api.auth import _create_jwt
from app.core.config import settings
from app.core.deps import get_current_user


def test_create_jwt_contains_expected_claims():
    token = _create_jwt("user-123")
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])

    assert payload["sub"] == "user-123"
    assert "exp" in payload


def test_get_current_user_accepts_valid_token(make_user, fake_db):
    user = make_user()
    token = _create_jwt(str(user.id))
    fake_db.query.return_value.filter.return_value.first.return_value = user

    result = get_current_user(authorization=f"Bearer {token}", db=fake_db)

    assert result is user


def test_get_current_user_rejects_missing_bearer_prefix(fake_db):
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization="not-a-bearer-token", db=fake_db)

    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_expired_token(fake_db):
    expired_payload = {"sub": "user-123", "exp": datetime.utcnow() - timedelta(minutes=1)}
    expired_token = jwt.encode(expired_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=f"Bearer {expired_token}", db=fake_db)

    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_bad_signature(fake_db):
    forged_token = jwt.encode({"sub": "user-123"}, "wrong-secret", algorithm=settings.jwt_algorithm)

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=f"Bearer {forged_token}", db=fake_db)

    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_token_for_deleted_user(fake_db):
    token = _create_jwt("00000000-0000-0000-0000-000000000000")
    fake_db.query.return_value.filter.return_value.first.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=f"Bearer {token}", db=fake_db)

    assert exc_info.value.status_code == 401
