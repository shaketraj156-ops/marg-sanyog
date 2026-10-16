from datetime import timedelta

import jwt
import pytest

from app.config import get_settings
from app.core.errors import ProblemError
from app.core.security import (
    ALGORITHM,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_hash_is_argon2id_and_salted():
    first, second = hash_password("secret"), hash_password("secret")
    assert first.startswith("$argon2id$")
    assert first != second


def test_verify_password():
    hashed = hash_password("secret")
    assert verify_password(hashed, "secret")
    assert not verify_password(hashed, "other")


def test_verify_password_with_garbage_hash_is_false():
    assert not verify_password("not-a-hash", "secret")


def test_access_token_round_trip():
    claims = decode_token(create_access_token(42), "access")
    assert claims["sub"] == "42"
    assert claims["type"] == "access"


def test_refresh_token_round_trip_returns_jti_and_expiry():
    token, jti, expires_at = create_refresh_token(7)
    claims = decode_token(token, "refresh")
    assert claims["sub"] == "7"
    assert claims["jti"] == jti
    assert expires_at.tzinfo is not None


def test_refresh_token_is_not_accepted_as_access_token():
    token, _, _ = create_refresh_token(7)
    with pytest.raises(ProblemError) as err:
        decode_token(token, "access")
    assert err.value.status == 401


def test_access_token_is_not_accepted_as_refresh_token():
    with pytest.raises(ProblemError) as err:
        decode_token(create_access_token(7), "refresh")
    assert err.value.status == 401


def test_expired_token_has_its_own_code():
    token = create_access_token(1, lifetime=timedelta(seconds=-10))
    with pytest.raises(ProblemError) as err:
        decode_token(token, "access")
    assert (err.value.status, err.value.code) == (401, "token_expired")


def test_token_signed_with_another_secret_is_rejected():
    forged = jwt.encode(
        {"sub": "1", "type": "access", "jti": "x", "exp": 9999999999},
        "some-other-secret-that-is-also-long-enough-123456",
        algorithm=ALGORITHM,
    )
    with pytest.raises(ProblemError) as err:
        decode_token(forged, "access")
    assert err.value.code == "invalid_token"


def test_unsigned_token_is_rejected():
    unsigned = jwt.encode({"sub": "1", "type": "access", "jti": "x", "exp": 9999999999}, None, algorithm="none")
    with pytest.raises(ProblemError):
        decode_token(unsigned, "access")


def test_token_missing_required_claims_is_rejected():
    incomplete = jwt.encode({"sub": "1"}, get_settings().jwt_secret, algorithm=ALGORITHM)
    with pytest.raises(ProblemError):
        decode_token(incomplete, "access")


def test_non_numeric_subject_is_rejected():
    bad = jwt.encode(
        {"sub": "abc", "type": "access", "jti": "x", "exp": 9999999999},
        get_settings().jwt_secret,
        algorithm=ALGORITHM,
    )
    with pytest.raises(ProblemError):
        decode_token(bad, "access")


def test_garbage_is_rejected():
    with pytest.raises(ProblemError):
        decode_token("not.a.token", "access")
