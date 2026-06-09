"""HR News Digest module.

Автоматическая агрегация HR-новостей из 10 источников:
- 8 веб-сайтов (Firecrawl API)
- 2 Telegram каналов (Telethon)

Функционал:
- Автоматический сбор новостей
- AI-резюмирование (Together AI / Qwen 2.5 7B)
- Категоризация по темам
- Ежедневная отправка в Telegram (08:00)
"""

from biotact.modules.news_digest.service import DigestService

__all__ = ["DigestService"]
