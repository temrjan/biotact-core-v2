"""Integration tests for HR chat flow with mocked OpenAI (PR-11)."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from biotact.core.config import Settings, get_settings
from biotact.main import app

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from httpx import AsyncClient

pytestmark = pytest.mark.integration


def _hr_settings() -> Settings:
    return Settings(
        app_env="development",
        debug=False,
        secret_key="test-secret-key-for-testing-only",
        postgres_host="localhost",
        postgres_port=5432,
        postgres_user="biotact",
        postgres_password="biotact_test",
        postgres_db="biotact_test",
        openai_api_key="sk-test-key",
        hr_allowed_emails="test@biotact.uz",
    )


@pytest.fixture
def hr_allow() -> Generator[None, None, None]:
    app.dependency_overrides[get_settings] = _hr_settings
    yield
    app.dependency_overrides.pop(get_settings, None)


@pytest_asyncio.fixture
async def hr_client(
    authenticated_client: AsyncClient,
    hr_allow: None,
) -> AsyncClient:
    return authenticated_client


def _make_docx(path: Path) -> None:
    from docx import Document

    doc = Document()
    doc.add_paragraph("Name: {{ FIO }}")
    doc.save(str(path))


def _mock_openai_response(tool_name: str, tool_args: str, final_text: str = "Готово"):
    """Build two-round mock: first tool call, then final message."""

    class _Func:
        name: ClassVar[str] = tool_name
        arguments: ClassVar[str] = tool_args

    class _ToolCall:
        id: ClassVar[str] = "call_123"
        function: ClassVar[_Func] = _Func()

    class _MsgTool:
        content: ClassVar[None] = None
        tool_calls: ClassVar[list[_ToolCall]] = [_ToolCall()]

    class _ChoiceTool:
        finish_reason: ClassVar[str] = "tool_calls"
        message: ClassVar[_MsgTool] = _MsgTool()

    class _MsgFinal:
        content: ClassVar[str] = final_text
        tool_calls: ClassVar[None] = None

    class _ChoiceFinal:
        finish_reason: ClassVar[str] = "stop"
        message: ClassVar[_MsgFinal] = _MsgFinal()

    class _ResponseTool:
        choices: ClassVar[list[_ChoiceTool]] = [_ChoiceTool()]

    class _ResponseFinal:
        choices: ClassVar[list[_ChoiceFinal]] = [_ChoiceFinal()]

    calls = [_ResponseTool(), _ResponseFinal()]
    idx = 0

    async def _create(*_a, **_k):
        nonlocal idx
        resp = calls[idx]
        idx += 1
        return resp

    return _create


class TestChatFlow:
    """Chat → tool call → document generation with mocked OpenAI."""

    @pytest.mark.asyncio
    async def test_chat_generates_document(
        self, hr_client: AsyncClient, tmp_path: Path
    ) -> None:
        docx = tmp_path / "chat_tpl.docx"
        _make_docx(docx)

        with docx.open("rb") as f:
            files = {
                "file": (
                    "chat_tpl.docx",
                    f,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            }
            r = await hr_client.post("/api/v1/hr/library?category=td_chat", files=files)
        assert r.status_code == 201
        tpl_id = r.json()["id"]

        mock_create = _mock_openai_response(
            "generate_document",
            f'{{"template_id": {tpl_id}, "data": {{"FIO": "Иванов Иван Иванович"}}}}',
        )

        with patch("biotact.modules.hr.chat.service.AsyncOpenAI") as MockClient:
            instance = MockClient.return_value
            instance.chat.completions.create = AsyncMock(side_effect=mock_create)

            payload = {"message": "Создай трудовой договор для Иванова", "history": []}
            chat_r = await hr_client.post("/api/v1/hr/chat/message", json=payload)

        assert chat_r.status_code == 200
        body = chat_r.json()
        assert body["document_url"] is not None
        assert "/api/v1/hr/documents/download/" in body["document_url"]

    @pytest.mark.asyncio
    async def test_chat_without_tool_returns_text_only(
        self, hr_client: AsyncClient
    ) -> None:
        class _Msg:
            content: ClassVar[str] = "Привет, чем могу помочь?"
            tool_calls: ClassVar[None] = None

        class _Choice:
            finish_reason: ClassVar[str] = "stop"
            message: ClassVar[_Msg] = _Msg()

        class _Resp:
            choices: ClassVar[list[_Choice]] = [_Choice()]

        with patch("biotact.modules.hr.chat.service.AsyncOpenAI") as MockClient:
            instance = MockClient.return_value
            instance.chat.completions.create = AsyncMock(return_value=_Resp())

            payload = {"message": "Привет", "history": []}
            r = await hr_client.post("/api/v1/hr/chat/message", json=payload)

        assert r.status_code == 200
        body = r.json()
        assert body["message"] == "Привет, чем могу помочь?"
        assert body["document_url"] is None
