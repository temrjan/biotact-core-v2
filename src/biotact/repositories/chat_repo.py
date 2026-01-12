"""Chat repository."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from biotact.models.chat import ChatMessage, ChatSession


def generate_session_id() -> str:
    """Generate unique session ID."""
    return f"sess_{uuid.uuid4().hex[:12]}"


def generate_message_id() -> str:
    """Generate unique message ID."""
    return f"msg_{uuid.uuid4().hex[:12]}"


class ChatRepository:
    """Repository for Chat operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_session_by_id(self, session_id: str) -> ChatSession | None:
        """Get chat session by session_id."""
        result = await self.session.execute(
            select(ChatSession).where(ChatSession.session_id == session_id)
        )
        return result.scalar_one_or_none()

    async def get_sessions_by_user(
        self,
        user_id: int,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[ChatSession], int]:
        """Get chat sessions for a user with pagination."""
        # Get total count
        count_result = await self.session.execute(
            select(func.count(ChatSession.id)).where(ChatSession.user_id == user_id)
        )
        total = count_result.scalar_one()

        # Get sessions
        result = await self.session.execute(
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        sessions = list(result.scalars().all())

        return sessions, total

    async def create_session(
        self, user_id: int, title: str = "New Chat"
    ) -> ChatSession:
        """Create a new chat session."""
        chat_session = ChatSession(
            session_id=generate_session_id(),
            title=title,
            user_id=user_id,
        )
        self.session.add(chat_session)
        await self.session.flush()
        await self.session.refresh(chat_session)
        return chat_session

    async def update_session_title(
        self,
        chat_session: ChatSession,
        title: str,
    ) -> ChatSession:
        """Update session title."""
        chat_session.title = title
        await self.session.flush()
        await self.session.refresh(chat_session)
        return chat_session

    async def add_message(
        self,
        session_id: int,
        role: str,
        content: str,
    ) -> ChatMessage:
        """Add a message to a session."""
        message = ChatMessage(
            message_id=generate_message_id(),
            session_id=session_id,
            role=role,
            content=content,
        )
        self.session.add(message)
        await self.session.flush()
        await self.session.refresh(message)
        return message

    async def get_messages_by_session(
        self,
        session_id: int,
        limit: int = 50,
    ) -> list[ChatMessage]:
        """Get messages for a session."""
        result = await self.session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())
