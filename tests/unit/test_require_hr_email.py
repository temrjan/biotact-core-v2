"""Tests for HR email allowlist authorization."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, status

from biotact.core.config import Settings
from biotact.core.dependencies import _parse_hr_allowlist, require_hr_email
from biotact.models.user import User


def _fake_user(email: str) -> User:
    """Build a User stub with just the email field set."""
    user = MagicMock(spec=User)
    user.email = email
    return user


def _settings_with(emails: str) -> Settings:
    """Build a Settings instance with hr_allowed_emails preset."""
    s = MagicMock(spec=Settings)
    s.hr_allowed_emails = emails
    return s


@pytest.mark.unit
class TestParseHrAllowlist:
    """Tests for _parse_hr_allowlist normalization."""

    def test_empty_string_returns_empty_set(self) -> None:
        assert _parse_hr_allowlist("") == frozenset()

    def test_whitespace_only_returns_empty_set(self) -> None:
        assert _parse_hr_allowlist("   , , ") == frozenset()

    def test_lowercases_and_trims(self) -> None:
        result = _parse_hr_allowlist(" Admin@Biotact.UZ , hr@biotact.uz ")
        assert result == frozenset({"admin@biotact.uz", "hr@biotact.uz"})

    def test_dedups(self) -> None:
        result = _parse_hr_allowlist("a@x.uz,a@x.uz,A@X.UZ")
        assert result == frozenset({"a@x.uz"})


@pytest.mark.unit
class TestRequireHrEmail:
    """Tests for require_hr_email dependency."""

    async def test_allows_user_in_allowlist(self) -> None:
        user = _fake_user("hr@biotact.uz")
        settings = _settings_with("admin@biotact.uz,hr@biotact.uz")
        result = await require_hr_email(user, settings)
        assert result is user

    async def test_case_insensitive_match(self) -> None:
        user = _fake_user("HR@Biotact.UZ")
        settings = _settings_with("hr@biotact.uz")
        result = await require_hr_email(user, settings)
        assert result is user

    async def test_rejects_user_not_in_allowlist(self) -> None:
        user = _fake_user("employee@biotact.uz")
        settings = _settings_with("admin@biotact.uz,hr@biotact.uz")
        with pytest.raises(HTTPException) as exc_info:
            await require_hr_email(user, settings)
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    async def test_empty_allowlist_rejects_everyone(self) -> None:
        """Fail-closed: empty HR_ALLOWED_EMAILS means no HR access."""
        user = _fake_user("admin@biotact.uz")
        settings = _settings_with("")
        with pytest.raises(HTTPException) as exc_info:
            await require_hr_email(user, settings)
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
