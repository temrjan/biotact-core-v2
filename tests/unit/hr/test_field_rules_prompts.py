"""Single source of per-category field rules feeds BOTH extraction prompts.

Guards the PR-A core: the fallback extractor and the system prompt draw the
same per-category rules, so document-specific fields (``GPD_NUMBER`` /
``GPD_DATE`` …) can no longer be known to one prompt and missing from the other.
"""

from __future__ import annotations

from biotact.modules.hr.chat.field_rules import (
    COMMON_FIELD_RULES,
    DOC_TYPE_RULES,
    build_extractor_rules,
    build_system_rules,
)
from biotact.modules.hr.chat.prompts import SYSTEM_PROMPT


class TestExtractorRules:
    """The fallback extractor gets common + the requested category's rules."""

    def test_nda_gpd_includes_gpd_number_and_date(self) -> None:
        rules = build_extractor_rules("nda_gpd")
        assert "GPD_NUMBER" in rules
        assert "GPD_DATE" in rules

    def test_td_includes_contract_type(self) -> None:
        assert "CONTRACT_TYPE" in build_extractor_rules("td_osnovnoy")

    def test_includes_common_block(self) -> None:
        assert COMMON_FIELD_RULES in build_extractor_rules("nda_gpd")
        assert COMMON_FIELD_RULES in build_extractor_rules("td_osnovnoy")

    def test_category_gets_only_its_own_block(self) -> None:
        gpd = build_extractor_rules("nda_gpd")
        assert "GPD_NUMBER" in gpd
        # prikaz_avto's field must not bleed into an unrelated category.
        assert "CAR_BRAND" not in gpd

    def test_unknown_category_degrades_to_common(self) -> None:
        # A freshly uploaded template with a new category must not raise on the
        # very path this module exists to make reliable.
        rules = build_extractor_rules("brand_new_category")
        assert rules == COMMON_FIELD_RULES
        assert "GPD_NUMBER" not in rules


class TestSystemRules:
    """The system prompt gets common + every category."""

    def test_covers_every_category(self) -> None:
        rules = build_system_rules()
        for doc_type in DOC_TYPE_RULES:
            assert doc_type.render() in rules

    def test_shares_common_source_with_extractor(self) -> None:
        # Same COMMON text in both assembled prompts == one source, no drift.
        assert COMMON_FIELD_RULES in build_system_rules()
        assert COMMON_FIELD_RULES in build_extractor_rules("nda_gpd")

    def test_deterministic_for_prompt_cache(self) -> None:
        assert build_system_rules() == build_system_rules()


class TestSystemPrompt:
    """The module-level SYSTEM_PROMPT embeds the assembled rules."""

    def test_embeds_system_rules(self) -> None:
        assert build_system_rules() in SYSTEM_PROMPT

    def test_contains_gpd_rule(self) -> None:
        assert "GPD_NUMBER" in SYSTEM_PROMPT
