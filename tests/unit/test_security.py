"""Tests for security module."""

from datetime import timedelta

import pytest

from biotact.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_password,
    verify_password,
)


@pytest.mark.unit
class TestPasswordHashing:
    """Tests for password hashing functions."""

    def test_hash_password_returns_hash(self) -> None:
        """hash_password should return a bcrypt hash."""
        password = "mysecretpassword"
        hashed = hash_password(password)

        assert hashed != password
        assert hashed.startswith("$2b$")  # bcrypt prefix

    def test_hash_password_different_each_time(self) -> None:
        """hash_password should return different hashes for same password."""
        password = "mysecretpassword"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        assert hash1 != hash2  # Different salts

    def test_verify_password_correct(self) -> None:
        """verify_password should return True for correct password."""
        password = "mysecretpassword"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self) -> None:
        """verify_password should return False for incorrect password."""
        password = "mysecretpassword"
        hashed = hash_password(password)

        assert verify_password("wrongpassword", hashed) is False

    def test_verify_password_empty(self) -> None:
        """verify_password should return False for empty password."""
        hashed = hash_password("mysecretpassword")

        assert verify_password("", hashed) is False


@pytest.mark.unit
class TestJWTTokens:
    """Tests for JWT token functions."""

    def test_create_access_token(self) -> None:
        """create_access_token should return a JWT string."""
        data = {"sub": "123", "department_id": "marketing"}
        token = create_access_token(data)

        assert isinstance(token, str)
        assert len(token) > 0
        assert token.count(".") == 2  # JWT format: header.payload.signature

    def test_decode_access_token(self) -> None:
        """decode_access_token should return the original payload."""
        data = {"sub": "123", "department_id": "marketing"}
        token = create_access_token(data)

        payload = decode_access_token(token)

        assert payload["sub"] == "123"
        assert payload["department_id"] == "marketing"
        assert "exp" in payload

    def test_decode_invalid_token(self) -> None:
        """decode_access_token should raise TokenError for invalid token."""
        with pytest.raises(TokenError):
            decode_access_token("invalid.token.here")

    def test_decode_expired_token(self) -> None:
        """decode_access_token should raise TokenError for expired token."""
        data = {"sub": "123"}
        token = create_access_token(data, expires_delta=timedelta(seconds=-1))

        with pytest.raises(TokenError):
            decode_access_token(token)

    def test_create_access_token_custom_expiry(self) -> None:
        """create_access_token should accept custom expiry."""
        data = {"sub": "123"}
        token = create_access_token(data, expires_delta=timedelta(hours=2))

        payload = decode_access_token(token)
        assert payload["sub"] == "123"

    def test_create_refresh_token(self) -> None:
        """create_refresh_token should create a valid token."""
        data = {"sub": "123"}
        token = create_refresh_token(data)

        payload = decode_access_token(token)
        assert payload["sub"] == "123"

    def test_token_contains_expiration(self) -> None:
        """Token payload should contain expiration claim."""
        data = {"sub": "123"}
        token = create_access_token(data)

        payload = decode_access_token(token)
        assert "exp" in payload
