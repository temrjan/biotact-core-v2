# ADR 001: Модульный монолит как архитектурный паттерн

**Дата:** 2026-01-12
**Статус:** Accepted
**Deciders:** Temrjan

## Context

Biotact Platform v1 представляет собой неструктурированный монолит с единственным файлом main.py (35KB), содержащим всю логику приложения. Это создаёт проблемы с тестированием, поддержкой и расширением.

Нужно выбрать архитектурный подход для v2, который:
- Позволит структурировать код
- Упростит тестирование
- Не добавит избыточной сложности
- Подойдёт для команды из 1 человека

## Decision

Выбираем **модульный монолит** — архитектуру, где приложение разделено на логические модули с чёткими границами, но деплоится как единый процесс.

### Структура модулей:

```
src/biotact/
├── core/           # Shared infrastructure (config, db, security)
├── models/         # Domain models (SQLAlchemy)
├── schemas/        # DTOs (Pydantic)
├── repositories/   # Data access layer
├── services/       # Business logic
├── api/v1/         # HTTP endpoints
├── modules/        # Department-specific logic
│   ├── marketing/
│   ├── sales/
│   └── call_center/
└── rag/            # RAG engine
```

### Правила границ модулей:

1. **Модули общаются через интерфейсы** — не напрямую обращаются к внутренностям друг друга
2. **Dependency injection** — зависимости передаются явно через конструкторы/FastAPI Depends
3. **Один модуль = одна ответственность** — Single Responsibility Principle

## Consequences

### Positive

- **Testability:** Каждый модуль тестируется изолированно с mock-зависимостями
- **Maintainability:** Легко найти и изменить код, связанный с конкретной функцией
- **Simplicity:** Один процесс, один деплой, нет distributed complexity
- **Flexibility:** При росте можно выделить модуль в микросервис

### Negative

- **Shared failure domain:** Падение одного модуля = падение всего приложения
- **No independent scaling:** Нельзя масштабировать только RAG модуль
- **Discipline required:** Нужно следить за соблюдением границ модулей

### Neutral

- **Learning curve:** Требуется понимание принципов модульной архитектуры
- **Refactoring path:** Чёткий путь к микросервисам при необходимости

## Alternatives Considered

### Микросервисы
Отклонено: избыточная сложность для текущего масштаба (100 req/day, 1 разработчик).

### Классический монолит
Отклонено: это текущее состояние, которое создаёт проблемы с тестированием и поддержкой.

## References

- RFC 001: Архитектура Biotact Platform v2
- [Modular Monolith: A Primer](https://www.kamilgrzybek.com/design/modular-monolith-primer/)
