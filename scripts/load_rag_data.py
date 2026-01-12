"""Load knowledge base data into Qdrant for RAG."""

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from biotact.core.config import Settings
from biotact.services.rag.embedding import EmbeddingService


# Knowledge base data for each department
KNOWLEDGE_BASE = {
    "callcenter": [
        {
            "content": "Biotact - узбекский бренд профессиональной косметики для лица и тела. Основан в 2019 году. Производство в Узбекистане с использованием натуральных ингредиентов.",
            "source": "company_info.txt",
        },
        {
            "content": "Способы оплаты: наличные при доставке, карта Uzcard/Humo, перевод на карту. Минимальная сумма заказа - 100,000 сум.",
            "source": "payment_info.txt",
        },
        {
            "content": "Доставка по Ташкенту - бесплатно при заказе от 200,000 сум. Доставка по регионам через Yandex, CDEK. Срок доставки: Ташкент 1-2 дня, регионы 3-5 дней.",
            "source": "delivery_info.txt",
        },
        {
            "content": "Возврат товара возможен в течение 14 дней при сохранении упаковки и товарного вида. Для возврата свяжитесь с нами по телефону +998 71 123 45 67.",
            "source": "return_policy.txt",
        },
        {
            "content": "Линейка продуктов: кремы для лица (дневной, ночной, увлажняющий), сыворотки (витамин C, гиалуроновая кислота), маски для лица, средства для тела.",
            "source": "products_info.txt",
        },
        {
            "content": "Популярные продукты: Крем дневной увлажняющий (89,000 сум), Сыворотка с витамином C (129,000 сум), Маска для лица очищающая (59,000 сум).",
            "source": "bestsellers.txt",
        },
        {
            "content": "График работы call-центра: Пн-Пт 9:00-18:00, Сб 10:00-15:00. Воскресенье - выходной. Телефон: +998 71 123 45 67.",
            "source": "working_hours.txt",
        },
        {
            "content": "Частые вопросы: Как отследить заказ? - Вам придет SMS с номером отслеживания. Можно ли изменить адрес доставки? - Да, позвоните нам до отправки заказа.",
            "source": "faq.txt",
        },
    ],
    "marketing": [
        {
            "content": "Целевая аудитория Biotact: женщины 25-45 лет, средний+ доход, интересуются уходом за собой, активны в социальных сетях.",
            "source": "target_audience.txt",
        },
        {
            "content": "Tone of voice бренда: профессиональный, заботливый, современный. Избегаем: агрессивных продаж, сравнений с конкурентами.",
            "source": "brand_voice.txt",
        },
        {
            "content": "Хэштеги для Instagram: #biotact #biotactuz #косметикаузбекистан #уходзалицом #натуральнаякосметика #красотаузбекистан",
            "source": "hashtags.txt",
        },
        {
            "content": "Контент-план: Пн - отзывы клиентов, Вт - обучающий контент, Ср - новинки/акции, Чт - behind the scenes, Пт - пользовательский контент, Сб - развлекательный.",
            "source": "content_plan.txt",
        },
        {
            "content": "KPI маркетинга: охват Instagram 50K+/месяц, вовлеченность 5%+, конверсия из соцсетей 2%, CAC < 30,000 сум.",
            "source": "marketing_kpi.txt",
        },
        {
            "content": "Рекламные каналы: Instagram (основной), Telegram, Facebook. Бюджет распределение: Instagram 60%, Telegram 25%, другие 15%.",
            "source": "ad_channels.txt",
        },
    ],
    "hr": [
        {
            "content": "Открытые вакансии: Менеджер по продажам (от 5 млн сум), SMM-специалист (от 4 млн сум), Оператор call-центра (от 3 млн сум).",
            "source": "vacancies.txt",
        },
        {
            "content": "Процесс найма: 1) Отклик на вакансию, 2) Телефонное интервью, 3) Собеседование в офисе, 4) Тестовое задание (для некоторых позиций), 5) Оффер.",
            "source": "hiring_process.txt",
        },
        {
            "content": "Онбординг нового сотрудника: День 1 - знакомство с командой, документы. Неделя 1 - обучение продуктам. Месяц 1 - работа с наставником.",
            "source": "onboarding.txt",
        },
        {
            "content": "Льготы сотрудников: скидка 40% на продукцию, бесплатные обеды, гибкий график для удаленных позиций, корпоративные мероприятия.",
            "source": "benefits.txt",
        },
        {
            "content": "Корпоративные ценности: Качество во всем, Забота о клиентах, Командная работа, Постоянное развитие.",
            "source": "values.txt",
        },
    ],
    "dashboard": [
        {
            "content": "Финансовый год компании: январь-декабрь. Квартальная отчетность. Основные метрики: выручка, расходы, маржинальность, ROI.",
            "source": "finance_basics.txt",
        },
        {
            "content": "Категории расходов: marketing (маркетинг), salary (зарплаты), office (офис), logistics (логистика), production (производство).",
            "source": "expense_categories.txt",
        },
        {
            "content": "Формат добавления транзакций через чат: 'добавь расход 500000 на маркетинг' или 'запиши доход 2000000 от продаж'.",
            "source": "transaction_format.txt",
        },
        {
            "content": "Целевые показатели 2026: выручка 5 млрд сум, маржинальность 35%, рост продаж 25% г/г.",
            "source": "targets_2026.txt",
        },
    ],
    "sales": [
        {
            "content": "Скрипт продаж: Приветствие -> Выявление потребностей -> Презентация продукта -> Работа с возражениями -> Закрытие сделки.",
            "source": "sales_script.txt",
        },
        {
            "content": "Работа с возражениями. 'Дорого': Сравните с салонными процедурами, наш крем хватит на 2 месяца. 'Подумаю': Что именно смущает? Давайте разберем.",
            "source": "objections.txt",
        },
        {
            "content": "Допродажи: К дневному крему предложи ночной (-15% при покупке комплекта). К сыворотке - увлажняющий крем.",
            "source": "upselling.txt",
        },
        {
            "content": "Акции: При покупке от 300K - подарок миниатюра. Приведи подругу - обеим скидка 10%. День рождения - скидка 20%.",
            "source": "promotions.txt",
        },
    ],
}


async def create_collection(client: AsyncQdrantClient, collection_name: str) -> None:
    """Create Qdrant collection if not exists."""
    collections = await client.get_collections()
    existing = [c.name for c in collections.collections]

    if collection_name in existing:
        print(f"Collection '{collection_name}' already exists")
        return

    # text-embedding-3-large has 3072 dimensions
    await client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=3072, distance=Distance.COSINE),
    )
    print(f"Created collection '{collection_name}'")


async def load_data(
    client: AsyncQdrantClient,
    embedding_service: EmbeddingService,
    collection_name: str,
) -> None:
    """Load knowledge base data into Qdrant."""
    points = []

    for department_id, documents in KNOWLEDGE_BASE.items():
        print(f"\nProcessing {department_id}...")

        for doc in documents:
            # Generate embedding
            vector = await embedding_service.embed_text(doc["content"])

            point = PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={
                    "content": doc["content"],
                    "source": doc["source"],
                    "department_id": department_id,
                },
            )
            points.append(point)
            print(f"  + {doc['source']}")

    # Upsert all points
    await client.upsert(collection_name=collection_name, points=points)
    print(f"\n✓ Loaded {len(points)} documents into Qdrant")


async def main() -> None:
    """Main function."""
    print("=" * 50)
    print("Biotact RAG Data Loader")
    print("=" * 50)

    settings = Settings()

    # Initialize services
    client = AsyncQdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
    )
    embedding_service = EmbeddingService(settings)

    collection_name = settings.qdrant_collection

    # Create collection
    await create_collection(client, collection_name)

    # Load data
    await load_data(client, embedding_service, collection_name)

    print("\n✓ RAG data loading complete!")


if __name__ == "__main__":
    asyncio.run(main())
