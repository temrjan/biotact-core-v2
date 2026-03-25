"""AskBiotact shared constants — single source of truth.

Product catalog, prices, phone patterns, price triggers, and enrichment helpers.
Used by both webhook bot and public API adapters.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# =============================================================================
# Product Catalog
# =============================================================================


@dataclass(frozen=True, slots=True)
class Product:
    """Product catalog item."""

    name: str
    price: int
    category: str  # "probiotics" | "vitamins" | "kitchen"
    description: str
    image_url: str = ""


CATEGORIES: dict[str, str] = {
    "probiotics": "\U0001f9a0 Пробиотики",
    "vitamins": "\U0001f48a Витамины и комплексы",
    "kitchen": "\U0001f373 Кухонная техника",
}

PRODUCTS: dict[str, Product] = {
    "bifolak_neo": Product(
        name="BIFOLAK NEO",
        price=61_000,
        category="probiotics",
        description=(
            "Синбиотик нового поколения для восстановления микрофлоры "
            "кишечника. Содержит пробиотики и пребиотики."
        ),
    ),
    "bifolak_active": Product(
        name="BIFOLAK ACTIVE",
        price=69_000,
        category="probiotics",
        description=(
            "Усиленная формула с повышенной концентрацией полезных "
            "бактерий для активной поддержки пищеварения."
        ),
    ),
    "bifolak_zincum": Product(
        name="BIFOLAK ZINCUM",
        price=69_000,
        category="probiotics",
        description=(
            "Пробиотик с цинком для укрепления иммунитета "
            "и поддержки микрофлоры кишечника."
        ),
    ),
    "bifolak_magniy": Product(
        name="BIFOLAK MAGNIY",
        price=76_000,
        category="probiotics",
        description=(
            "Пробиотик с магнием для поддержки нервной системы, "
            "снижения стресса и нормализации пищеварения."
        ),
    ),
    "bifolak_zincum_cd3": Product(
        name="BIFOLAK ZINCUM+C+D3",
        price=76_000,
        category="probiotics",
        description=(
            "Комплексная формула: пробиотики + цинк + витамин C + D3 "
            "для максимальной поддержки иммунитета."
        ),
    ),
    "calciy_triactive": Product(
        name="CALCIY TRIACTIVE D3",
        price=76_000,
        category="vitamins",
        description=(
            "Тройная формула кальция с витамином D3 для укрепления "
            "костей, зубов и суставов."
        ),
    ),
    "immunocomplex": Product(
        name="IMMUNOCOMPLEX",
        price=76_000,
        category="vitamins",
        description=(
            "Комплекс для укрепления иммунитета с витаминами, "
            "минералами и растительными экстрактами."
        ),
    ),
    "immunocomplex_kids": Product(
        name="IMMUNOCOMPLEX KIDS",
        price=76_000,
        category="vitamins",
        description=(
            "Детский иммунокомплекс с мягкой формулой, "
            "адаптированной для детского организма."
        ),
    ),
    "dermacomplex": Product(
        name="DERMACOMPLEX",
        price=94_000,
        category="vitamins",
        description=(
            "Комплекс для здоровья кожи, волос и ногтей. "
            "Содержит коллаген, биотин и антиоксиданты."
        ),
    ),
    "neurocomplex_kids": Product(
        name="NEUROCOMPLEX KIDS",
        price=101_000,
        category="vitamins",
        description=(
            "Детский нейрокомплекс для поддержки развития мозга, "
            "внимания и когнитивных функций."
        ),
    ),
    "ophtalmocomplex": Product(
        name="OPHTALMOCOMPLEX",
        price=123_000,
        category="vitamins",
        description=(
            "Комплекс для здоровья глаз с лютеином, зеаксантином "
            "и черникой. Защита зрения."
        ),
    ),
    "aerogrill": Product(
        name="Аэрогриль BIOTACT",
        price=850_000,
        category="kitchen",
        description=(
            "Многофункциональный аэрогриль для здорового приготовления "
            "без масла. Гриль, выпечка, сушка."
        ),
    ),
    "juicer": Product(
        name="Соковыжималка BIOTACT",
        price=820_000,
        category="kitchen",
        description=(
            "Мощная соковыжималка для свежевыжатых соков "
            "из фруктов и овощей каждый день."
        ),
    ),
    "hand_blender": Product(
        name="Ручной блендер BIOTACT",
        price=320_000,
        category="kitchen",
        description="Компактный ручной блендер для смузи, супов-пюре и детского питания.",
    ),
    "elec_blender": Product(
        name="Электрический блендер BIOTACT",
        price=320_000,
        category="kitchen",
        description=(
            "Стационарный блендер с мощным мотором для смузи, коктейлей и измельчения."
        ),
    ),
    "toaster": Product(
        name="Тостер BIOTACT",
        price=255_000,
        category="kitchen",
        description=(
            "Стильный тостер с регулировкой прожарки для идеальных тостов каждое утро."
        ),
    ),
    "food_processor": Product(
        name="Кухонный комбайн BIOTACT",
        price=230_000,
        category="kitchen",
        description=(
            "Универсальный кухонный комбайн: нарезка, шинковка, "
            "замес теста и многое другое."
        ),
    ),
    "elec_kettle": Product(
        name="Электрический чайник BIOTACT",
        price=160_000,
        category="kitchen",
        description=(
            "Быстрый электрический чайник из нержавеющей стали с автоотключением."
        ),
    ),
}

# Derived lookups
PRODUCT_PRICES: dict[str, int] = {p.name: p.price for p in PRODUCTS.values()}

# Product names for enrichment (ordered: longer names first for greedy match)
PRODUCT_NAMES: list[str] = [
    "BIFOLAK ACTIVE",
    "BIFOLAK NEO",
    "BIFOLAK MAGNIY",
    "BIFOLAK ZINCUM",
    "BIFOLAK",
    "IMMUNOCOMPLEX KIDS",
    "IMMUNOCOMPLEX",
    "NEUROCOMPLEX KIDS",
    "NEUROCOMPLEX",
    "DERMACOMPLEX",
    "OPHTALMOCOMPLEX",
    "CALCIY TRIACTIVE",
    "CALCIY",
]


# =============================================================================
# Phone Patterns (Uzbekistan)
# =============================================================================

PHONE_PATTERNS: list[str] = [
    r"\+?998[\s-]?\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}",
    r"998\d{9}",
    r"\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}",
]


def extract_phone(text: str) -> str | None:
    """Extract and normalize phone number from text."""
    for pattern in PHONE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            return match.group().replace(" ", "").replace("-", "")
    return None


# =============================================================================
# Price Query Detection
# =============================================================================

PRICE_TRIGGERS: list[str] = [
    # Russian
    "цена",
    "стоимость",
    "сколько стоит",
    "почем",
    "прайс",
    "стоит",
    "дорого",
    "дешево",
    "купить",
    "заказать",
    "оплата",
    # Uzbek
    "narx",
    "qancha",
    "qimmat",
    "arzon",
    "sotib olish",
    "buyurtma",
    "tolov",
    "pul",
    "som",
    "sum",
]

PRICE_ENRICHMENT: str = (
    "цены на продукты BIOTACT прайс-лист стоимость narxlar BIOTACT mahsulotlari"
)

# Order detection keywords
ORDER_KEYWORDS: list[str] = [
    "заказ",
    "купить",
    "оформ",
    "доставк",
    "адрес",
    "телефон",
    "имя",
]


# =============================================================================
# Query Enrichment Helpers
# =============================================================================


def extract_products_from_history(history: list[dict[str, str]]) -> list[str]:
    """Extract product names mentioned in recent chat history."""
    text = " ".join(m.get("content", "") for m in history[-6:])
    text_upper = text.upper()
    return [p for p in PRODUCT_NAMES if p.upper() in text_upper]


def is_short_query(message: str) -> bool:
    """Check if query is short/incomplete and needs context enrichment."""
    short_patterns = [
        r"^.{1,30}$",
        r"(?:какой|что|как|сколько|состав|цена|дозировка|применение|курс)",
    ]
    message_lower = message.lower()
    return any(re.search(p, message_lower) for p in short_patterns)


def is_price_query(message: str) -> bool:
    """Check if message is about prices."""
    message_lower = message.lower()
    return any(trigger in message_lower for trigger in PRICE_TRIGGERS)


def enrich_query(message: str, history: list[dict[str, str]]) -> str:
    """Enrich query with context for better RAG search.

    1. Short/ambiguous queries: prepend product names from history.
    2. Price queries: add price semantic core for matching prices.txt.
    """
    enriched = message

    if is_short_query(message) and history:
        products = extract_products_from_history(history)
        if products:
            enriched = f"{' '.join(products)} {message}"
        else:
            recent_user_msgs = [
                m["content"] for m in history[-6:] if m.get("role") == "user"
            ][-2:]
            if recent_user_msgs:
                enriched = f"{' '.join(recent_user_msgs)} {message}"

    if is_price_query(message):
        enriched = f"{enriched} {PRICE_ENRICHMENT}"

    return enriched


def get_slug_by_product_name(name: str) -> str | None:
    """Find product slug by display name."""
    for slug, product in PRODUCTS.items():
        if product.name == name:
            return slug
    return None


def format_product_card(product: Product) -> str:
    """Format product info as an HTML card caption."""
    price_fmt = f"{product.price:,}".replace(",", " ")
    return (
        f"<b>{product.name}</b>\n\n{product.description}\n\n\U0001f4b0 {price_fmt} сум"
    )
