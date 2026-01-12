"""Test AskBiotact bot with realistic conversation scenario."""

import asyncio
import json
import sys
from pathlib import Path
from typing import List, Dict, Any

sys.path.insert(0, str(Path(__file__).parent / "biotact-core-v2" / "src"))

from biotact.core.config import Settings
from biotact.services.rag import EmbeddingService, LLMService, QdrantService
from biotact.modules.askbiotact.config import askbiotact_config


class ConversationTester:
    """Test bot conversation with realistic scenario."""

    def __init__(self):
        self.settings = Settings()
        self.messages: List[Dict[str, str]] = []
        self.llm_service = None
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
        self.llm_service = LLMService(self.settings)
        print("✅ Сервисы готовы\n")

    async def get_bot_response(self, user_message: str) -> str:
        """Get bot response using RAG + LLM."""

        # Generate embedding for query
        query_vector = await self.embedding_service.embed_text(user_message)

        # Retrieve relevant knowledge
        rag_results = await self.qdrant_service.search(
            query_vector=query_vector,
            department_id="askbiotact",
            limit=5,
            score_threshold=0.30
        )

        # Build chat history in correct format (last 6 messages)
        chat_history = self.messages[-6:] if self.messages else None

        # Get response from LLM
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
        print("🧪 ТЕСТИРОВАНИЕ ASKBIOTACT BOT")
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
        self.print_message("AskBiotact", bot_response, "🤖")

        await asyncio.sleep(1)

        # Step 2: Provide context
        user_msg = "Мне 32 года. Это началось после родов, я кормлю грудью сейчас."
        self.print_message("Алина", user_msg, "👤")

        bot_response = await self.get_bot_response(user_msg)
        self.print_message("AskBiotact", bot_response, "🤖")

        await asyncio.sleep(1)

        # Step 3: Ask about side effects or additional problems
        user_msg = "Ещё ногти стали ломкими и постоянно устаю. Это нормально?"
        self.print_message("Алина", user_msg, "👤")

        bot_response = await self.get_bot_response(user_msg)
        self.print_message("AskBiotact", bot_response, "🤖")

        await asyncio.sleep(1)

        # Step 4: Show interest in recommendation
        user_msg = "Расскажите подробнее про рекомендованный продукт. Как его принимать?"
        self.print_message("Алина", user_msg, "👤")

        bot_response = await self.get_bot_response(user_msg)
        self.print_message("AskBiotact", bot_response, "🤖")

        await asyncio.sleep(1)

        # Step 5: Ask about price and decide
        user_msg = "Хорошо, меня устраивает. Сколько стоит и как заказать?"
        self.print_message("Алина", user_msg, "👤")

        bot_response = await self.get_bot_response(user_msg)
        self.print_message("AskBiotact", bot_response, "🤖")

        await asyncio.sleep(1)

        # Step 6: Place order
        user_msg = f"""Хочу заказать!

📦 DERMACOMPLEX, 1 упаковка
👤 {self.persona['name']}
📞 {self.persona['phone']}
📍 {self.persona['address']}"""

        self.print_message("Алина", user_msg, "👤")

        bot_response = await self.get_bot_response(user_msg)
        self.print_message("AskBiotact", bot_response, "🤖")

        await asyncio.sleep(1)

        # Step 7: Confirm order
        user_msg = "Да, всё верно! Подтверждаю заказ."
        self.print_message("Алина", user_msg, "👤")

        bot_response = await self.get_bot_response(user_msg)
        self.print_message("AskBiotact", bot_response, "🤖")

    async def analyze_conversation(self):
        """Analyze conversation quality."""

        print("\n\n" + "═" * 70)
        print("📊 АНАЛИЗ КАЧЕСТВА ДИАЛОГА")
        print("═" * 70)

        # Count messages
        user_msgs = [m for m in self.messages if m["role"] == "user"]
        bot_msgs = [m for m in self.messages if m["role"] == "assistant"]

        print(f"\n📈 Статистика:")
        print(f"  • Сообщений от пользователя: {len(user_msgs)}")
        print(f"  • Ответов бота: {len(bot_msgs)}")

        # Check key elements
        full_conversation = " ".join([m["content"] for m in bot_msgs])

        checks = {
            "✅ Эмпатия присутствует": any(word in full_conversation.lower() for word in ["понимаю", "слышу", "поддержу", "помогу"]),
            "✅ Вопрос о возрасте": "лет" in full_conversation or "возраст" in full_conversation.lower(),
            "✅ Упоминание JTBD/задачи": any(word in full_conversation.lower() for word in ["укрепить", "восстановить", "поддержать", "улучшить"]),
            "✅ Указана цена": "сум" in full_conversation,
            "✅ Cross-sell предложение": len([m for m in bot_msgs if "также" in m["content"].lower() or "ещё" in m["content"].lower() or "дополнительно" in m["content"].lower()]) > 0,
            "✅ Инструкция по заказу": "имя" in full_conversation.lower() and "телефон" in full_conversation.lower(),
            "✅ Compliance (не лечит)": any(word in full_conversation.lower() for word in ["поддержка", "поддержать", "бад", "комплекс"]),
            "✅ Длина ответов адекватна": all(len(m["content"]) < 600 for m in bot_msgs)
        }

        print(f"\n🎯 Критерии качества:")
        for check, passed in checks.items():
            status = "✅" if passed else "❌"
            print(f"  {status} {check.replace('✅ ', '')}")

        # Calculate score
        score = sum(checks.values()) / len(checks) * 100

        print(f"\n🏆 ИТОГОВАЯ ОЦЕНКА: {score:.0f}%")

        if score >= 80:
            print("   Отлично! Бот работает как ожидалось.")
        elif score >= 60:
            print("   Хорошо, но есть что улучшить.")
        else:
            print("   ⚠️  Требуются доработки!")

        # Detailed findings
        print(f"\n📋 Детальная оценка:\n")

        # Check JTBD approach
        if any("JTBD" in m["content"] or "Jobs-to-be-Done" in m["content"] for m in bot_msgs):
            print("  ⚠️  Бот упомянул 'JTBD' напрямую - не должен использовать технический термин")

        # Check emoji usage
        emoji_count = sum(m["content"].count("💚") + m["content"].count("💛") + m["content"].count("✨") for m in bot_msgs)
        avg_emoji = emoji_count / len(bot_msgs) if bot_msgs else 0
        if avg_emoji > 2:
            print(f"  ⚠️  Слишком много эмодзи ({avg_emoji:.1f} на сообщение), рекомендуется 1-2")
        elif avg_emoji < 0.5:
            print(f"  ⚠️  Слишком мало эмодзи ({avg_emoji:.1f} на сообщение)")
        else:
            print(f"  ✅ Эмодзи использованы адекватно ({avg_emoji:.1f} на сообщение)")

        # Check response length
        avg_length = sum(len(m["content"]) for m in bot_msgs) / len(bot_msgs) if bot_msgs else 0
        if avg_length > 500:
            print(f"  ⚠️  Ответы слишком длинные (средняя {avg_length:.0f} символов)")
        elif avg_length < 200:
            print(f"  ⚠️  Ответы слишком короткие (средняя {avg_length:.0f} символов)")
        else:
            print(f"  ✅ Длина ответов оптимальна (средняя {avg_length:.0f} символов)")

        print("\n" + "═" * 70)
        print("✅ ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
        print("═" * 70)


async def main():
    """Main test function."""
    tester = ConversationTester()

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
