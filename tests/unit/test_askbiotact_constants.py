"""Unit tests for AskBiotact constants and enrichment helpers."""

import pytest

from biotact.modules.askbiotact.constants import (
    CATEGORIES,
    PRODUCT_NAMES,
    PRODUCT_PRICES,
    PRODUCTS,
    enrich_query,
    extract_phone,
    extract_products_from_history,
    format_product_card,
    get_slug_by_product_name,
    is_price_query,
    is_short_query,
)


class TestProductCatalog:
    """Tests for product catalog consistency."""

    def test_all_products_have_prices(self) -> None:
        for product in PRODUCTS.values():
            assert product.name in PRODUCT_PRICES
            assert PRODUCT_PRICES[product.name] == product.price

    def test_all_products_have_valid_category(self) -> None:
        for product in PRODUCTS.values():
            assert product.category in CATEGORIES

    def test_product_prices_positive(self) -> None:
        for name, price in PRODUCT_PRICES.items():
            assert price > 0, f"{name} has non-positive price"

    def test_get_slug_by_product_name(self) -> None:
        assert get_slug_by_product_name("BIFOLAK NEO") == "bifolak_neo"
        assert get_slug_by_product_name("NONEXISTENT") is None

    def test_format_product_card(self) -> None:
        product = PRODUCTS["bifolak_neo"]
        card = format_product_card(product)
        assert "BIFOLAK NEO" in card
        assert "61 000" in card
        assert "сум" in card


class TestPhoneExtraction:
    """Tests for phone number extraction."""

    def test_extract_uzbek_phone_with_plus(self) -> None:
        assert extract_phone("Мой номер +998901234567") == "+998901234567"

    def test_extract_uzbek_phone_without_plus(self) -> None:
        assert extract_phone("998901234567") == "998901234567"

    def test_extract_phone_with_spaces(self) -> None:
        result = extract_phone("+998 90 123 45 67")
        assert result is not None
        assert result.replace(" ", "").replace("-", "") == "+998901234567"

    def test_extract_phone_with_dashes(self) -> None:
        result = extract_phone("+998-90-123-45-67")
        assert result is not None
        assert "-" not in result

    def test_no_phone_in_text(self) -> None:
        assert extract_phone("Привет, как дела?") is None

    def test_short_number_pattern(self) -> None:
        result = extract_phone("90 123 45 67")
        assert result is not None


class TestQueryEnrichment:
    """Tests for query enrichment logic."""

    def test_is_short_query(self) -> None:
        assert is_short_query("цена") is True
        assert is_short_query("сколько стоит") is True
        assert is_short_query("какой состав") is True
        # Long query with keyword "состав" still matches (by design: keyword patterns)
        assert is_short_query("Расскажите подробнее о составе Bifolak Active") is True
        # Long query without any keywords is NOT short
        assert is_short_query("Мне нужна помощь с выбором продукта для всей семьи на длительный период") is False

    def test_is_price_query(self) -> None:
        assert is_price_query("сколько стоит биолак") is True
        assert is_price_query("qancha turadi") is True
        assert is_price_query("расскажи о составе") is False

    def test_extract_products_from_history(self) -> None:
        history = [
            {"role": "user", "content": "Расскажи про BIFOLAK NEO"},
            {"role": "assistant", "content": "BIFOLAK NEO — это синбиотик..."},
        ]
        products = extract_products_from_history(history)
        assert "BIFOLAK NEO" in products

    def test_extract_products_empty_history(self) -> None:
        assert extract_products_from_history([]) == []

    def test_enrich_short_query_with_product_history(self) -> None:
        history = [
            {"role": "user", "content": "Расскажи про IMMUNOCOMPLEX"},
            {"role": "assistant", "content": "IMMUNOCOMPLEX — это комплекс..."},
        ]
        enriched = enrich_query("сколько стоит", history)
        assert "IMMUNOCOMPLEX" in enriched

    def test_enrich_no_keyword_query_unchanged(self) -> None:
        history = [{"role": "user", "content": "test"}]
        # Query without enrichment trigger keywords stays unchanged
        long_msg = "Мне нужна помощь с выбором продукта для всей семьи на длительный период"
        enriched = enrich_query(long_msg, history)
        assert enriched == long_msg

    def test_enrich_price_query_adds_semantic_core(self) -> None:
        enriched = enrich_query("цена на биолак", [])
        assert "прайс-лист" in enriched


@pytest.mark.parametrize(
    "product_name",
    PRODUCT_NAMES,
)
def test_product_names_found_in_catalog(product_name: str) -> None:
    """Each PRODUCT_NAME should match at least one product in the catalog."""
    found = any(
        product_name.upper() in p.name.upper()
        for p in PRODUCTS.values()
    )
    assert found, f"PRODUCT_NAME '{product_name}' not found in catalog"
