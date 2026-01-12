# ADR 002: Payload-based multitenancy в Qdrant

**Дата:** 2026-01-12
**Статус:** Accepted
**Deciders:** Temrjan

## Context

Biotact Platform обслуживает 5 отделов компании (Marketing, Sales, Call Center, Logistics, Accounting). Каждый отдел имеет свою базу знаний для RAG-системы.

Нужно выбрать стратегию изоляции данных отделов в Qdrant (векторная БД).

## Decision

Выбираем **payload-based multitenancy** — все документы хранятся в одной коллекции, изоляция через фильтр по `department_id` в payload.

### Реализация:

```python
# Структура документа
{
    "id": "doc_123",
    "vector": [0.1, 0.2, ...],  # embedding
    "payload": {
        "department_id": "marketing",  # tenant identifier
        "content": "...",
        "source": "...",
        "created_at": "2026-01-12T10:00:00Z"
    }
}

# Поиск с фильтром
qdrant_client.search(
    collection_name="biotact_knowledge",
    query_vector=query_embedding,
    query_filter=Filter(
        must=[
            FieldCondition(
                key="department_id",
                match=MatchValue(value="marketing")
            )
        ]
    ),
    limit=10
)
```

### Индексация:

```python
# Создание payload index для быстрой фильтрации
qdrant_client.create_payload_index(
    collection_name="biotact_knowledge",
    field_name="department_id",
    field_schema=PayloadSchemaType.KEYWORD
)
```

## Consequences

### Positive

- **Простота:** Одна коллекция, простое управление
- **Эффективность:** Qdrant оптимизирован для фильтрации по payload
- **Гибкость:** Легко добавить новый отдел без изменения структуры
- **Экономия ресурсов:** Меньше overhead чем отдельные коллекции

### Negative

- **Риск утечки данных:** При ошибке в фильтре можно получить чужие данные
- **Нет физической изоляции:** Все данные в одном месте
- **Масштабирование:** При росте до миллионов документов может потребоваться шардирование

### Mitigation

- **Обязательный фильтр:** Все запросы к Qdrant проходят через сервисный слой, который ВСЕГДА добавляет `department_id` фильтр
- **Тесты:** Integration тесты проверяют изоляцию данных
- **Audit log:** Логирование всех запросов к RAG

## Alternatives Considered

### Отдельные коллекции для каждого отдела
```
biotact_marketing
biotact_sales
biotact_call_center
```

**Отклонено:**
- Больше операционной сложности (5+ коллекций)
- Сложнее добавлять новые отделы
- Для 5 отделов избыточно

### Namespace-based (если бы Qdrant поддерживал)
**Отклонено:** Qdrant не имеет встроенных namespaces как Pinecone.

## References

- [Qdrant Filtering Documentation](https://qdrant.tech/documentation/concepts/filtering/)
- [Multitenancy Patterns](https://qdrant.tech/documentation/guides/multiple-partitions/)
