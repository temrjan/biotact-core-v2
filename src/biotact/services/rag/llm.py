"""LLM service for generating responses (OpenAI or Anthropic)."""

from anthropic import AsyncAnthropic
from anthropic.types import TextBlock
from openai import AsyncOpenAI

from biotact.core.config import Settings
from biotact.services.rag.qdrant import SearchResult

SYSTEM_PROMPT = """Ты AI-ассистент фармацевтической компании Biotact.
Твоя задача - помогать сотрудникам компании, отвечая на вопросы на основе предоставленного контекста.

Правила:
1. Отвечай только на основе предоставленного контекста
2. Если информации недостаточно, честно скажи об этом
3. Будь вежлив и профессионален
4. Давай четкие и структурированные ответы
5. Если вопрос касается цен или наличия товара, указывай источник информации
6. Не выдумывай информацию, которой нет в контексте"""


class LLMService:
    """Service for generating responses using OpenAI or Anthropic."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.provider = settings.llm_provider
        self.model = settings.llm_model

        self._anthropic_client: AsyncAnthropic | None = None
        self._openai_client: AsyncOpenAI | None = None

        if self.provider == "anthropic":
            self._anthropic_client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        else:  # openai
            self._openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def generate_response(
        self,
        question: str,
        context: list[SearchResult] | None = None,
        chat_history: list[dict[str, str]] | None = None,
        system_prompt: str | None = None,
        user_message_template: str | None = None,
        max_tokens: int = 1000,
        temperature: float = 0.3,
    ) -> str:
        """Generate a response based on question and context.

        Args:
            question: User's question.
            context: Retrieved context from vector search (optional).
            chat_history: Previous messages in conversation.
            system_prompt: Custom system prompt (uses default if None).
            user_message_template: Custom template for user message.
            max_tokens: Maximum tokens in response.
            temperature: Response creativity (0-1).

        Returns:
            Generated response text.
        """
        # Build user message
        if context:
            context_text = self._build_context(context)
            if user_message_template:
                user_message = user_message_template.format(
                    context=context_text,
                    question=question,
                )
            else:
                user_message = f"""Контекст:
{context_text}

Вопрос: {question}

Ответь на вопрос, используя только предоставленный контекст."""
        else:
            user_message = question

        if self.provider == "anthropic":
            return await self._generate_anthropic(
                user_message=user_message,
                chat_history=chat_history,
                system_prompt=system_prompt or SYSTEM_PROMPT,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        else:  # openai
            return await self._generate_openai(
                user_message=user_message,
                chat_history=chat_history,
                system_prompt=system_prompt or SYSTEM_PROMPT,
                max_tokens=max_tokens,
                temperature=temperature,
            )

    async def _generate_anthropic(
        self,
        user_message: str,
        chat_history: list[dict[str, str]] | None,
        system_prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        """Generate response using Anthropic Claude."""
        assert self._anthropic_client is not None

        messages: list[dict[str, str]] = []

        if chat_history:
            messages.extend(chat_history[-10:])

        messages.append({"role": "user", "content": user_message})

        response = await self._anthropic_client.messages.create(
            model=self.model,
            system=system_prompt,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=max_tokens,
            temperature=temperature,
        )

        text_block = next(b for b in response.content if isinstance(b, TextBlock))
        return text_block.text

    async def _generate_openai(
        self,
        user_message: str,
        chat_history: list[dict[str, str]] | None,
        system_prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        """Generate response using OpenAI."""
        assert self._openai_client is not None

        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
        ]

        if chat_history:
            messages.extend(chat_history[-10:])

        messages.append({"role": "user", "content": user_message})

        # gpt-5/o1+ models require max_completion_tokens and do not support temperature
        # Reasoning models use tokens for internal reasoning, so need higher limit
        new_api = self._needs_new_token_param()
        effective_tokens = max_tokens * 3 if new_api else max_tokens
        params: dict[str, object] = {
            "model": self.model,
            "messages": messages,
        }
        params["max_completion_tokens" if new_api else "max_tokens"] = effective_tokens
        if not new_api:
            params["temperature"] = temperature
        response = await self._openai_client.chat.completions.create(**params)  # type: ignore[call-overload]

        return response.choices[0].message.content or ""

    def _needs_new_token_param(self) -> bool:
        """Check if model requires max_completion_tokens instead of max_tokens."""
        model = self.model.lower()
        return any(k in model for k in ("gpt-5", "o1", "o3", "o4"))

    def _build_context(self, results: list[SearchResult]) -> str:
        """Build context string from search results."""
        if not results:
            return "Релевантный контекст не найден."

        context_parts = []
        for i, result in enumerate(results, 1):
            source_info = f"[Источник: {result.source}]"
            context_parts.append(f"{i}. {result.content}\n   {source_info}")

        return "\n\n".join(context_parts)

    async def generate_title(self, first_message: str) -> str:
        """Generate a short title for chat session."""
        system_text = "Создай короткий заголовок (3-5 слов) для чата на основе первого сообщения. Отвечай только заголовком, без кавычек."

        if self.provider == "anthropic":
            assert self._anthropic_client is not None
            anthropic_response = await self._anthropic_client.messages.create(
                model=self.model,
                system=system_text,
                messages=[{"role": "user", "content": first_message}],
                max_tokens=20,
                temperature=0.5,
            )
            text_block = next(
                b for b in anthropic_response.content if isinstance(b, TextBlock)
            )
            title = text_block.text
        else:  # openai
            assert self._openai_client is not None
            new_api = self._needs_new_token_param()
            params2: dict[str, object] = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_text},
                    {"role": "user", "content": first_message},
                ],
            }
            params2["max_completion_tokens" if new_api else "max_tokens"] = (
                200 if new_api else 20
            )
            if not new_api:
                params2["temperature"] = 0.5
            openai_response = await self._openai_client.chat.completions.create(
                **params2
            )  # type: ignore[call-overload]
            title = openai_response.choices[0].message.content or first_message[:50]

        return title.strip()
