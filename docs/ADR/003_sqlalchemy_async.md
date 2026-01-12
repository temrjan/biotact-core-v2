# ADR 003: SQLAlchemy 2.0 с async/await

**Дата:** 2026-01-12
**Статус:** Accepted
**Deciders:** Temrjan

## Context

Biotact Platform использует PostgreSQL для хранения пользователей, сессий чата и метаданных. FastAPI — асинхронный фреймворк, и для максимальной производительности нужен асинхронный доступ к БД.

Нужно выбрать ORM/query builder для работы с PostgreSQL.

## Decision

Выбираем **SQLAlchemy 2.0** с **asyncpg** драйвером и полностью асинхронным API.

### Конфигурация:

```python
# core/database.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql+asyncpg://user:pass@localhost:5432/biotact"

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=5,
    max_overflow=10,
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
```

### Модели (SQLAlchemy 2.0 style):

```python
# models/user.py
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String
from .base import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    department_id: Mapped[str] = mapped_column(String(50), index=True)
```

### Repository pattern:

```python
# repositories/user_repo.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.user import User

class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()
```

## Consequences

### Positive

- **Performance:** Асинхронные запросы не блокируют event loop
- **Type safety:** SQLAlchemy 2.0 с `Mapped[]` обеспечивает type hints
- **FastAPI integration:** Нативная поддержка async в dependencies
- **Mature ecosystem:** Alembic для миграций, богатая документация
- **Flexibility:** Можно использовать как ORM, так и Core для сложных запросов

### Negative

- **Learning curve:** SQLAlchemy 2.0 syntax отличается от 1.x
- **Async complexity:** Нужно понимать async context managers
- **N+1 queries:** Требуется внимательность с eager/lazy loading

### Mitigation

- **Strict typing:** `mypy --strict` для выявления проблем с типами
- **Query logging:** `echo=True` в dev для отслеживания N+1
- **Eager loading:** Явное использование `selectinload()` / `joinedload()`

## Alternatives Considered

### Tortoise ORM
**Отклонено:**
- Менее зрелый экосистем
- Меньше документации и community support
- Ограниченные возможности миграций

### Raw asyncpg
**Отклонено:**
- Нет ORM абстракции
- Больше boilerplate кода
- Сложнее поддерживать

### SQLModel (Pydantic + SQLAlchemy)
**Рассмотрено, но отложено:**
- Интересный подход (одна модель для ORM и Pydantic)
- Менее гибкий для сложных случаев
- Можно мигрировать позже при необходимости

## References

- [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/)
- [asyncpg Documentation](https://magicstack.github.io/asyncpg/)
- [FastAPI + SQLAlchemy](https://fastapi.tiangolo.com/tutorial/sql-databases/)
