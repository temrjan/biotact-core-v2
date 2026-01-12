"""Security utilities: JWT tokens and password hashing."""

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from biotact.core.config import get_settings


class TokenError(Exception):
    """Raised when token validation fails."""

    pass


def hash_password(password: str) -> str:
    """Hash a password using bcrypt.

    Args:
        password: Plain text password.

    Returns:
        Hashed password string.

    Example:
        hashed = hash_password("mysecretpassword")
    """
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash.

    Args:
        plain_password: Plain text password to verify.
        hashed_password: Hashed password to compare against.

    Returns:
        True if password matches, False otherwise.

    Example:
        if verify_password("mysecret", user.hashed_password):
            print("Password correct!")
    """
    password_bytes = plain_password.encode("utf-8")
    hashed_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hashed_bytes)


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT access token.

    Args:
        data: Payload data to encode in the token.
        expires_delta: Optional custom expiration time.
            If not provided, uses settings.jwt_expire_minutes.

    Returns:
        Encoded JWT token string.

    Example:
        token = create_access_token(
            data={"sub": str(user.id), "department_id": user.department_id}
        )
    """
    settings = get_settings()
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)

    to_encode.update({"exp": expire})

    return jwt.encode(
        to_encode,
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token.

    Args:
        token: JWT token string to decode.

    Returns:
        Decoded token payload.

    Raises:
        TokenError: If token is invalid or expired.

    Example:
        try:
            payload = decode_access_token(token)
            user_id = payload.get("sub")
        except TokenError:
            raise HTTPException(status_code=401)
    """
    settings = get_settings()

    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError as e:
        raise TokenError(f"Invalid token: {e}") from e


def create_refresh_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT refresh token with longer expiration.

    Args:
        data: Payload data to encode in the token.
        expires_delta: Optional custom expiration time.
            Defaults to 7 days.

    Returns:
        Encoded JWT refresh token string.
    """
    if expires_delta is None:
        expires_delta = timedelta(days=7)

    return create_access_token(data, expires_delta)
