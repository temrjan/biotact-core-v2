"""Test AskBiotact bot with Anthropic Claude instead of OpenAI."""

import asyncio
import os
import sys
from pathlib import Path
from typing import List, Dict

sys.path.insert(0, str(Path(__file__).parent / "biotact-core-v2" / "src"))

from anthropic import AsyncAnthropic
from biotact.core.config import Settings
from biotact.services.rag import EmbeddingService, QdrantService
from biotact.modules.askbiotact.config import askbiotact_config


class AnthropicLLMService:
    """LLM service using Anthropic Claude."""

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001"):
        self.client = AsyncAnthropic(api_key=api_key)
        self.model = model
        print(f"🤖 Используется модель: {model}")

    async def generate_response(
        self,
        question: str,
        context: list,
        chat_history: list[dict[str, str]] | None = None,
        system_prompt: str | None = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ) -> str:
        """Generate response using Claude."""

        # Build context from search results
        context_parts = []
        for i, result in enumerate(context, 1):
            source_info = f"[Источник: {result.source}]"
            context_parts.append(f"{i}. {result.content}\n   {source_info}")

        context_text = "\n\n".join(context_parts) if context_parts else "Релевантный контекст не найден."

        # Build messages
        messages = []

        # Add chat history
        if chat_history:
            messages.extend(chat_history[-10:])

        # Add current question with context
        user_message = f"""Контекст:
{context_text}

Вопрос: {question}

Ответь на вопрос, используя только предоставленный контекст."""

        messages.append({"role": "user", "content": user_message})

        # Call Claude API
        response = await self.client.messages.create(
            model=self.model,
            system=system_prompt or "Ты AI-ассистент BIOTACT.",
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        return response.content[0].text


class ConversationTester:
    """Test bot conversation with Anthropic Claude."""

    def __init__(self, anthropic_api_key: str):
        self.settings = Settings()
        self.messages: List[Dict[str, str]] = []
        self.llm_service = AnthropicLLMService(anthropic_api_key)
        self.qdrant_service = None
        self.embedding_service = None

        # Persona
        self.persona = {
            "name": "Алина",
            "age": 32,
            "problem": "Выпадение волос после родов",
            "context": "Кормит грудью, 2 месяца после родов, стресс, усталость",
            "phone": "+998 90 123 45 67",
            "address": "Ташкент, Яккасарайский район, ул. Бабура 45, кв. 12"
        }

    async def initialize(self):
        """Initialize services."""
        print("🔧 Инициализация сервисов...")
        self.embedding_service = EmbeddingService(self.settings)
        self.qdrant_service = QdrantService(self.settings)
        print("✅ Сервисы готовы\n")

    async def get_bot_response(self, user_message: str) -> str:
        """Get bot response using RAG + Anthropic Claude."""

        # Generate embedding for query
        query_vector = await self.embedding_service.embed_text(user_message)

        # Retrieve relevant knowledge
        rag_results = await self.qdrant_service.search(
            query_vector=query_vector,
            department_id="askbiotact",
            limit=5,
            score_threshold=0.30
        )

        # Build chat history
        chat_history = self.messages[-6:] if self.messages else None

        # Get response from Claude
        bot_response = await self.llm_service.generate_response(
            question=user_message,
            context=rag_results,
            chat_history=chat_history,
            system_prompt=askbiotact_config.system_prompt,
            temperature=0.7,
            max_tokens=800
        )

        # Add to conversation history
        self.messages.append({"role": "user", "content": user_message})
        self.messages.append({"role": "assistant", "content": bot_response})

        return bot_response

    def print_message(self, sender: str, message: str, emoji: str = ""):
        """Pretty print message."""
        print(f"\n{emoji} {sender}:")
        print(f"{'─' * 70}")
        print(message)
        print(f"{'─' * 70}")

    async def run_conversation(self):
        """Run full conversation scenario."""

        print("═" * 70)
        print("🧪 ТЕСТИРОВАНИЕ ASKBIOTACT BOT (ANTHROPIC CLAUDE SONNET)")
        print("═" * 70)
        print(f"\n👤 ПЕРСОНАЖ: {self.persona['name']}, {self.persona['age']} лет")
        print(f"❗ ПРОБЛЕМА: {self.persona['problem']}")
        print(f"📝 КОНТЕКСТ: {self.persona['context']}")
        print("\n" + "═" * 70)
        print("💬 НАЧАЛО ДИАЛОГА")
        print("═" * 70)

        # Step 1: Initial problem statement
        user_msg = "Здравствуйте! У меня сильно выпадают волосы уже 2 месяца, не знаю что делать 😔"
        self.print_message("Алина", user_msg, "👤")

        bot_response = await self.get_bot_response(user_msg)
        self.print_message("AskBiotact (Claude)", bot_response, "🤖")

        await asyncio.sleep(1)

        # Step 2: Provide context
        user_msg = "Мне 32 года. Это началось после родов, я кормлю грудью сейчас."
        self.print_message("Алина", user_msg, "👤")

        bot_response = await self.get_bot_response(user_msg)
        self.print_message("AskBiotact (Claude)", bot_response, "🤖")

        await asyncio.sleep(1)

        # Step 3: Ask about side effects
        user_msg = "Ещё ногти стали ломкими и постоянно устаю. Это нормально?"
        self.print_message("Алина", user_msg, "👤")

        bot_response = await self.get_bot_response(user_msg)
        self.print_message("AskBiotact (Claude)", bot_response, "🤖")

        await asyncio.sleep(1)

        # Step 4: Show interest
        user_msg = "Расскажите подробнее про рекомендованный продукт. Как его принимать?"
        self.print_message("Алина", user_msg, "👤")

        bot_response = await self.get_bot_response(user_msg)
        self.print_message("AskBiotact (Claude)", bot_response, "🤖")

        await asyncio.sleep(1)

        # Step 5: Ask about price
        user_msg = "Хорошо, меня устраивает. Сколько стоит и как заказать?"
        self.print_message("Алина", user_msg, "👤")

        bot_response = await self.get_bot_response(user_msg)
        self.print_message("AskBiotact (Claude)", bot_response, "🤖")

        await asyncio.sleep(1)

        # Step 6: Place order
        user_msg = f"""Хочу заказать!

📦 DERMACOMPLEX, 1 упаковка
👤 {self.persona['name']}
📞 {self.persona['phone']}
📍 {self.persona['address']}"""

        self.print_message("Алина", user_msg, "👤")

        bot_response = await self.get_bot_response(user_msg)
        self.print_message("AskBiotact (Claude)", bot_response, "🤖")

        await asyncio.sleep(1)

        # Step 7: Confirm
        user_msg = "Да, всё верно! Подтверждаю заказ."
        self.print_message("Алина", user_msg, "👤")

        bot_response = await self.get_bot_response(user_msg)
        self.print_message("AskBiotact (Claude)", bot_response, "🤖")

    async def analyze_conversation(self):
        """Analyze conversation quality."""

        print("\n\n" + "═" * 70)
        print("📊 АНАЛИЗ КАЧЕСТВА ДИАЛОГА (CLAUDE SONNET)")
        print("═" * 70)

        user_msgs = [m for m in self.messages if m["role"] == "user"]
        bot_msgs = [m for m in self.messages if m["role"] == "assistant"]

        print(f"\n📈 Статистика:")
        print(f"  • Сообщений от пользователя: {len(user_msgs)}")
        print(f"  • Ответов бота: {len(bot_msgs)}")

        full_conversation = " ".join([m["content"] for m in bot_msgs])

        checks = {
            "✅ Эмпатия присутствует": any(word in full_conversation.lower() for word in ["понимаю", "слышу", "поддержу", "помогу"]),
            "✅ Вопрос о возрасте ПЕРВЫМ": "лет" in bot_msgs[0]["content"] or "возраст" in bot_msgs[0]["content"].lower(),
            "✅ Цена 94,000 указана": "94" in full_conversation and "000" in full_conversation,
            "✅ Cross-sell MAGNIY": "magniy" in full_conversation.lower() or "магний" in full_conversation.lower(),
            "✅ Compliance (не лечит)": any(word in full_conversation.lower() for word in ["поддержка", "поддержать", "бад", "комплекс", "врач"]),
            "✅ Длина ответов адекватна": all(len(m["content"]) < 600 for m in bot_msgs),
            "✅ Инструкция по заказу": "телефон" in full_conversation.lower() and "адрес" in full_conversation.lower(),
        }

        print(f"\n🎯 Критерии качества:")
        for check, passed in checks.items():
            status = "✅" if passed else "❌"
            print(f"  {status} {check.replace('✅ ', '')}")

        score = sum(checks.values()) / len(checks) * 100

        print(f"\n🏆 ИТОГОВАЯ ОЦЕНКА: {score:.0f}%")

        if score >= 85:
            print("   🎉 Отлично! Claude показал лучший результат!")
        elif score >= 75:
            print("   👍 Хорошо, сравнимо с OpenAI")
        else:
            print("   ⚠️  Требуются доработки")

        avg_length = sum(len(m["content"]) for m in bot_msgs) / len(bot_msgs) if bot_msgs else 0
        print(f"\n📏 Средняя длина ответов: {avg_length:.0f} символов")

        print("\n" + "═" * 70)
        print("✅ ТЕСТИРОВАНИЕ CLAUDE SONNET ЗАВЕРШЕНО")
        print("═" * 70)


async def main():
    """Main test function."""

    # Get Anthropic API key from environment or prompt
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    if not anthropic_key:
        print("❌ ANTHROPIC_API_KEY не найден в переменных окружения!")
        print("\nУстановите ключ:")
        print("  export ANTHROPIC_API_KEY='your-key-here'")
        print("\nИли передайте как аргумент скрипта")
        return

    print(f"✅ Используется Anthropic API Key: {anthropic_key[:20]}...")

    tester = ConversationTester(anthropic_key)

    try:
        await tester.initialize()
        await tester.run_conversation()
        await tester.analyze_conversation()

    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
