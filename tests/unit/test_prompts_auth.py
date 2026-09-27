"""Authorization and side effects of the prompts API."""

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from biotact.api.v1 import prompts
from biotact.core.dependencies import get_auth_service
from biotact.core.security import create_access_token
from biotact.main import app
from biotact.models.user import User
from biotact.repositories.user_repo import UserRepository
from biotact.services.auth_service import AuthService


class FakeUserRepository(UserRepository):
    """Keep the real authentication service independent of a database."""

    def __init__(self, users: dict[int, User]) -> None:
        self.users = users

    async def get_by_id(self, user_id: int) -> User | None:
        return self.users.get(user_id)


@pytest.fixture
def prompt_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, Path]]:
    prompt_path = tmp_path / "askbiotact.txt"
    prompt_path.write_text("original prompt", encoding="utf-8")
    monkeypatch.setattr(prompts, "PROMPTS_DIR", tmp_path)

    users = {
        1: User(
            id=1,
            email="admin@example.test",
            hashed_password="unused",
            full_name="Admin",
            department_id="admin",
            is_active=True,
        ),
        2: User(
            id=2,
            email="staff@example.test",
            hashed_password="unused",
            full_name="Staff",
            department_id="marketing",
            is_active=True,
        ),
        3: User(
            id=3,
            email="disabled@example.test",
            hashed_password="unused",
            full_name="Disabled Admin",
            department_id="admin",
            is_active=False,
        ),
    }
    app.dependency_overrides[get_auth_service] = lambda: AuthService(
        FakeUserRepository(users)
    )
    client = TestClient(app)
    try:
        yield client, prompt_path
    finally:
        client.close()
        app.dependency_overrides.pop(get_auth_service, None)


def token_headers(user_id: int, department_claim: str = "marketing") -> dict[str, str]:
    token = create_access_token(
        {"sub": str(user_id), "department_id": department_claim}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/prompts/askbiotact"),
        ("GET", "/api/v1/prompts/"),
        ("PUT", "/api/v1/prompts/askbiotact"),
    ],
)
def test_prompts_require_a_token(
    prompt_api: tuple[TestClient, Path], method: str, path: str
) -> None:
    client, prompt_path = prompt_api
    before_files = set(prompt_path.parent.iterdir())

    response = client.request(method, path, json={"content": "intrusion"})

    assert response.status_code == 401
    assert prompt_path.read_text(encoding="utf-8") == "original prompt"
    assert set(prompt_path.parent.iterdir()) == before_files


@pytest.mark.unit
@pytest.mark.parametrize("user_id", [1, 2])
def test_active_users_can_read_prompts(
    prompt_api: tuple[TestClient, Path], user_id: int
) -> None:
    client, _ = prompt_api

    response = client.get("/api/v1/prompts/askbiotact", headers=token_headers(user_id))
    listing = client.get("/api/v1/prompts/", headers=token_headers(user_id))

    assert response.status_code == 200
    assert response.json() == {"name": "askbiotact", "content": "original prompt"}
    assert listing.status_code == 200
    assert listing.json() == [{"name": "askbiotact", "content": "original prompt..."}]


@pytest.mark.unit
def test_non_admin_cannot_update_prompts_even_with_admin_claim(
    prompt_api: tuple[TestClient, Path],
) -> None:
    client, prompt_path = prompt_api
    before_files = set(prompt_path.parent.iterdir())

    response = client.put(
        "/api/v1/prompts/askbiotact",
        json={"content": "intrusion"},
        headers=token_headers(2, department_claim="admin"),
    )

    assert response.status_code == 403
    assert prompt_path.read_text(encoding="utf-8") == "original prompt"
    assert set(prompt_path.parent.iterdir()) == before_files


@pytest.mark.unit
@pytest.mark.parametrize(
    "headers",
    [
        {"Authorization": "Bearer invalid.token.here"},
        {
            "Authorization": "Bearer "
            + create_access_token({"sub": "1"}, expires_delta=timedelta(seconds=-1))
        },
        token_headers(3, department_claim="admin"),
        token_headers(999, department_claim="admin"),
    ],
    ids=["invalid-jwt", "expired-jwt", "inactive-admin", "unknown-user"],
)
def test_invalid_identity_cannot_update_prompts(
    prompt_api: tuple[TestClient, Path], headers: dict[str, str]
) -> None:
    client, prompt_path = prompt_api
    before_files = set(prompt_path.parent.iterdir())

    response = client.put(
        "/api/v1/prompts/askbiotact",
        json={"content": "intrusion"},
        headers=headers,
    )

    assert response.status_code == 401
    assert prompt_path.read_text(encoding="utf-8") == "original prompt"
    assert set(prompt_path.parent.iterdir()) == before_files


@pytest.mark.unit
def test_active_admin_can_update_prompt_with_backup(
    prompt_api: tuple[TestClient, Path],
) -> None:
    client, prompt_path = prompt_api

    response = client.put(
        "/api/v1/prompts/askbiotact",
        json={"content": "approved prompt"},
        headers=token_headers(1, department_claim="marketing"),
    )

    assert response.status_code == 200
    assert response.json() == {"name": "askbiotact", "content": "approved prompt"}
    assert prompt_path.read_text(encoding="utf-8") == "approved prompt"
    backups = list(prompt_path.parent.glob("askbiotact_backup_*.txt"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "original prompt"
