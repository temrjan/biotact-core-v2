"""Chat service for document search — OpenAI Function Calling + RAG.

Self-contained handler with folder/file awareness.
Pattern: same as hr/chat — DB context injection + multi-round function calling.
"""

import json
import logging
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from biotact.core.config import Settings
from biotact.modules.documents.repository import FileRepository
from biotact.modules.documents.schemas import FilesChatResponse, FilesChatSource
from biotact.modules.documents.vector_store import FileVectorStore
from biotact.services.rag.embedding import EmbeddingService

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# System prompt
# ═══════════════════════════════════════════════════════════════════

FILES_SYSTEM_PROMPT = """Ты AI-ассистент общей платформы документов компании Biotact.
Ты помогаешь сотрудникам искать информацию в загруженных документах и сопоставлять данные.

Возможности:
1. Поиск по содержимому всех документов
2. Сопоставление данных из разных файлов
3. Анализ и выводы на основе найденного
4. Просмотр структуры папок и файлов
5. Статистика хранилища

Правила:
- Отвечай ТОЛЬКО на основе найденного контекста из документов
- Если информации не найдено — честно скажи об этом
- Указывай имя файла-источника в ответе
- Отвечай на русском, кратко и по делу
- При сопоставлении указывай оба источника
"""

# ═══════════════════════════════════════════════════════════════════
# Tools for OpenAI function calling
# ═══════════════════════════════════════════════════════════════════

SEARCH_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_documents",
        "description": "Поиск по содержимому загруженных документов. Используй для любых вопросов о содержимом файлов.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Поисковый запрос — что искать в документах",
                },
            },
            "required": ["query"],
        },
    },
}

LIST_FOLDERS_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "list_folder_contents",
        "description": (
            "Показать содержимое папки — подпапки и файлы. "
            "Для корневого уровня передай folder_id = null."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "folder_id": {
                    "type": ["string", "null"],
                    "description": "UUID папки (folder_id) или null для корневого уровня",
                },
            },
            "required": ["folder_id"],
        },
    },
}

GET_STATS_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "get_storage_stats",
        "description": "Получить статистику хранилища: количество файлов, папок, размер, индексация.",
        "parameters": {"type": "object", "properties": {}},
    },
}

ALL_TOOLS = [SEARCH_TOOL, LIST_FOLDERS_TOOL, GET_STATS_TOOL]

MAX_ROUNDS = 5


class FilesChatService:
    """Chat service with RAG over uploaded documents + folder awareness.

    Flow (multi-round, up to 5 rounds):
    1. Build system prompt with folder/file context from DB
    2. Send user message to OpenAI with 3 tools
    3. If tool_call → execute → feed result back → loop
    4. When LLM returns text (no tool_call) → return as answer
    """

    def __init__(
        self,
        settings: Settings,
        embedding_service: EmbeddingService,
        vector_store: FileVectorStore,
        db: AsyncSession,
    ) -> None:
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
        self.embedding = embedding_service
        self.vector_store = vector_store
        self.repo = FileRepository(db)

    # ═══════════════════════════════════════════════════════════════
    # Public API
    # ═══════════════════════════════════════════════════════════════

    async def query(
        self,
        message: str,
        history: list[dict[str, str]] | None = None,
    ) -> FilesChatResponse:
        """Process chat message with optional RAG search.

        Args:
            message: User's question.
            history: Previous messages [{role, content}].

        Returns:
            FilesChatResponse with answer and sources.
        """
        # Build messages with dynamic context
        docs_ctx = await self._get_documents_context()

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": FILES_SYSTEM_PROMPT + docs_ctx},
        ]
        if history:
            messages.extend(history[-10:])
        messages.append({"role": "user", "content": message})

        all_sources: list[FilesChatSource] = []

        # Multi-round function calling loop
        for round_num in range(MAX_ROUNDS):
            try:
                response = await self.client.chat.completions.create(  # type: ignore[call-overload]
                    model=self.model,
                    messages=messages,
                    tools=ALL_TOOLS,
                    tool_choice="auto",
                    max_tokens=1000,
                    temperature=0.3,
                )
            except Exception as e:
                logger.error("OpenAI API error round=%d: %s", round_num, e)
                return FilesChatResponse(
                    answer="Ошибка при обработке запроса. Попробуйте позже.",
                    sources=[],
                )

            choice = response.choices[0].message

            # No tool calls → final answer
            if not choice.tool_calls:
                return FilesChatResponse(
                    answer=choice.content or "Не удалось обработать запрос.",
                    sources=all_sources,
                )

            # Process each tool call
            # Append assistant message with tool_calls
            messages.append(choice.model_dump(exclude_none=True))

            for tc in choice.tool_calls:
                func_name = tc.function.name
                try:
                    func_args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, AttributeError):
                    func_args = {}

                logger.info("Documents chat tool=%s args=%s", func_name, func_args)

                tool_result, sources = await self._execute_tool(
                    func_name,
                    func_args,
                    message,
                )
                all_sources.extend(sources)

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_result,
                    }
                )

        # Exhausted rounds
        return FilesChatResponse(
            answer="Не удалось обработать запрос за отведённое количество шагов.",
            sources=all_sources,
        )

    # ═══════════════════════════════════════════════════════════════
    # Context injection (like HR _get_template_context)
    # ═══════════════════════════════════════════════════════════════

    async def _get_documents_context(self) -> str:
        """Pre-fetch folder structure and stats for system prompt."""
        try:
            stats = await self.repo.get_stats()
            folders = await self.repo.get_folder_tree_summary()
        except Exception:
            logger.exception("Failed to load documents context")
            return ""

        # Stats block
        size_mb = round(stats["total_size"] / 1024 / 1024, 1)
        lines = [
            "\n\nСтатистика хранилища:",
            f"- Всего файлов: {stats['total_files']}, проиндексировано: {stats['indexed_files']}",
            f"- Всего папок: {stats['total_folders']}",
            f"- Общий размер: {size_mb} MB",
        ]

        # Folder tree (max 30 entries)
        if folders:
            lines.append("\nСтруктура папок:")
            # Build parent→children map for indentation
            children_map: dict[int | None, list[dict[str, Any]]] = {}
            for f in folders:
                parent = f["parent_id"]
                children_map.setdefault(parent, []).append(f)

            shown = 0
            max_shown = 30

            def _render(parent_id: int | None, indent: int) -> None:
                nonlocal shown
                for f in children_map.get(parent_id, []):
                    if shown >= max_shown:
                        return
                    prefix = "  " * indent + "- "
                    lines.append(f"{prefix}{f['name']} ({f['file_count']} файлов)")
                    shown += 1
                    _render(f["id"], indent + 1)

            _render(None, 0)

            if shown >= max_shown and len(folders) > max_shown:
                lines.append(f"  ... и ещё {len(folders) - max_shown} папок")

        # Root-level files count
        root_files = stats["total_files"] - sum(f["file_count"] for f in folders)
        if root_files > 0:
            lines.append(f"- (корневой уровень): {root_files} файлов")

        return "\n".join(lines)

    # ═══════════════════════════════════════════════════════════════
    # Tool execution
    # ═══════════════════════════════════════════════════════════════

    async def _execute_tool(
        self,
        name: str,
        args: dict[str, Any],
        original_message: str,
    ) -> tuple[str, list[FilesChatSource]]:
        """Execute tool call, return (result_text, sources)."""
        if name == "search_documents":
            return await self._tool_search(args, original_message)
        if name == "list_folder_contents":
            return await self._tool_list_folder(args)
        if name == "get_storage_stats":
            return await self._tool_stats()

        return f"Неизвестный инструмент: {name}", []

    async def _tool_search(
        self,
        args: dict[str, Any],
        original_message: str,
    ) -> tuple[str, list[FilesChatSource]]:
        """Search documents via RAG (embed → Qdrant → context)."""
        query = args.get("query", original_message)

        # Embed query
        query_vector = await self.embedding.embed_text(query)

        # Search Qdrant
        results = await self.vector_store.search(
            query_vector=query_vector,
            limit=5,
            score_threshold=0.3,
        )

        if not results:
            return "По запросу ничего не найдено в загруженных документах.", []

        # Build context + sources
        context_parts: list[str] = []
        sources: list[FilesChatSource] = []
        seen_files: set[str] = set()

        for r in results:
            file_name = str(r["file_name"])
            content = str(r["content"])
            score = float(r["score"])

            context_parts.append(f"[{file_name}]:\n{content}")

            if file_name not in seen_files:
                sources.append(FilesChatSource(file_name=file_name, score=score))
                seen_files.add(file_name)

        context_str = "\n\n---\n\n".join(context_parts)
        result_text = (
            f"Найденные фрагменты из документов:\n\n{context_str}\n\n"
            f"Ответь на основе этого контекста, указывая имена файлов-источников."
        )
        return result_text, sources

    async def _tool_list_folder(
        self,
        args: dict[str, Any],
    ) -> tuple[str, list[FilesChatSource]]:
        """List folder contents — subfolders and files."""
        folder_id = args.get("folder_id")

        # Resolve folder UUID → PK
        folder_pk: int | None = None
        folder_name = "Корневой уровень"
        if folder_id:
            folder = await self.repo.get_folder_by_uuid(str(folder_id))
            if not folder:
                return f"Папка с id '{folder_id}' не найдена.", []
            folder_pk = folder.id
            folder_name = folder.name

        # Get subfolders
        subfolders = await self.repo.list_folders(parent_id=folder_pk)
        # Get files
        files = await self.repo.list_files(folder_id=folder_pk)

        lines = [f"Содержимое: {folder_name}"]

        if subfolders:
            lines.append(f"\nПапки ({len(subfolders)}):")
            counts = await self.repo.get_folder_file_counts(
                [sf.id for sf in subfolders]
            )
            for sf in subfolders:
                count = counts.get(sf.id, 0)
                lines.append(f"  📁 {sf.name} ({count} файлов, id: {sf.folder_id})")

        if files:
            lines.append(f"\nФайлы ({len(files)}):")
            for f in files:
                size_kb = round(f.size / 1024, 1)
                indexed = "✓" if f.is_indexed else "⏳"
                lines.append(f"  📄 {f.name} ({size_kb} KB, {indexed})")

        if not subfolders and not files:
            lines.append("\nПусто — нет файлов и папок.")

        return "\n".join(lines), []

    async def _tool_stats(self) -> tuple[str, list[FilesChatSource]]:
        """Get storage statistics."""
        stats = await self.repo.get_stats()
        size_mb = round(stats["total_size"] / 1024 / 1024, 1)
        text = (
            f"Статистика хранилища:\n"
            f"- Файлов: {stats['total_files']}\n"
            f"- Проиндексировано: {stats['indexed_files']}\n"
            f"- Папок: {stats['total_folders']}\n"
            f"- Общий размер: {size_mb} MB"
        )
        return text, []
