"""Tests for RAG module configurations."""

import pytest

from biotact.modules import ModuleType, module_registry
from biotact.modules.base import RAGModuleConfig
from biotact.modules.callcenter.config import callcenter_config
from biotact.modules.hr.config import hr_config
from biotact.modules.marketing.config import marketing_config


class TestCallCenterConfig:
    """Tests for CallCenter module configuration."""

    @pytest.mark.unit
    def test_callcenter_config_has_correct_id(self) -> None:
        """CallCenter config should have correct department_id."""
        assert callcenter_config.department_id == "callcenter"

    @pytest.mark.unit
    def test_callcenter_config_is_rag_type(self) -> None:
        """CallCenter config should be RAG type."""
        assert callcenter_config.module_type == ModuleType.RAG

    @pytest.mark.unit
    def test_callcenter_config_has_system_prompt(self) -> None:
        """CallCenter config should have system prompt."""
        assert len(callcenter_config.system_prompt) > 100
        assert "BIOTACT" in callcenter_config.system_prompt

    @pytest.mark.unit
    def test_callcenter_config_has_department_filter(self) -> None:
        """CallCenter config should have department filter."""
        assert callcenter_config.department_filter == "callcenter"

    @pytest.mark.unit
    def test_callcenter_config_rag_parameters(self) -> None:
        """CallCenter config should have RAG parameters."""
        assert callcenter_config.rag_limit == 5
        assert callcenter_config.score_threshold == 0.35


class TestMarketingConfig:
    """Tests for Marketing module configuration."""

    @pytest.mark.unit
    def test_marketing_config_has_correct_id(self) -> None:
        """Marketing config should have correct department_id."""
        assert marketing_config.department_id == "marketing"

    @pytest.mark.unit
    def test_marketing_config_is_rag_type(self) -> None:
        """Marketing config should be RAG type."""
        assert marketing_config.module_type == ModuleType.RAG

    @pytest.mark.unit
    def test_marketing_config_has_system_prompt(self) -> None:
        """Marketing config should have system prompt."""
        assert len(marketing_config.system_prompt) > 100
        assert "маркетинг" in marketing_config.system_prompt.lower()

    @pytest.mark.unit
    def test_marketing_config_has_higher_rag_limit(self) -> None:
        """Marketing config should have higher rag_limit for more context."""
        assert marketing_config.rag_limit == 7


class TestHRConfig:
    """Tests for HR module configuration."""

    @pytest.mark.unit
    def test_hr_config_has_correct_id(self) -> None:
        """HR config should have correct department_id."""
        assert hr_config.department_id == "hr"

    @pytest.mark.unit
    def test_hr_config_is_rag_type(self) -> None:
        """HR config should be RAG type."""
        assert hr_config.module_type == ModuleType.RAG

    @pytest.mark.unit
    def test_hr_config_has_system_prompt(self) -> None:
        """HR config should have system prompt."""
        assert len(hr_config.system_prompt) > 100
        assert "HR" in hr_config.system_prompt or "кадр" in hr_config.system_prompt.lower()

    @pytest.mark.unit
    def test_hr_config_mentions_confidentiality(self) -> None:
        """HR config should mention data confidentiality."""
        prompt_lower = hr_config.system_prompt.lower()
        assert "конфиденциал" in prompt_lower or "персональн" in prompt_lower


class TestRAGModuleConfigBase:
    """Tests for RAGModuleConfig base class."""

    @pytest.mark.unit
    def test_rag_config_sets_department_filter_from_id(self) -> None:
        """RAGModuleConfig should auto-set department_filter from department_id."""
        config = RAGModuleConfig(
            department_id="test_dept",
            display_name="Test",
            description="Test module",
            system_prompt="Test prompt",
        )
        assert config.department_filter == "test_dept"

    @pytest.mark.unit
    def test_rag_config_respects_explicit_filter(self) -> None:
        """RAGModuleConfig should use explicit department_filter if provided."""
        config = RAGModuleConfig(
            department_id="test_dept",
            display_name="Test",
            description="Test module",
            system_prompt="Test prompt",
            department_filter="custom_filter",
        )
        assert config.department_filter == "custom_filter"

    @pytest.mark.unit
    def test_rag_config_get_system_message(self) -> None:
        """RAGModuleConfig.get_system_message should return prompt."""
        config = RAGModuleConfig(
            department_id="test",
            display_name="Test",
            description="Test",
            system_prompt="Base prompt here",
        )
        message = config.get_system_message()
        assert "Base prompt here" in message

    @pytest.mark.unit
    def test_rag_config_get_system_message_with_context(self) -> None:
        """RAGModuleConfig.get_system_message should handle context."""
        config = RAGModuleConfig(
            department_id="test",
            display_name="Test",
            description="Test",
            system_prompt="Base prompt",
        )
        context = {"retrieved_docs": ["doc1", "doc2", "doc3"]}
        message = config.get_system_message(context)
        assert "Base prompt" in message
        assert "3" in message  # Number of docs


class TestModuleRegistry:
    """Tests for module registry integration."""

    @pytest.fixture(autouse=True)
    def setup_registry(self) -> None:
        """Register modules before each test (ignore if already registered)."""
        for config in [callcenter_config, marketing_config, hr_config]:
            if module_registry.get(config.department_id) is None:
                module_registry.register(config)

    @pytest.mark.unit
    def test_registry_can_get_callcenter(self) -> None:
        """Registry should return callcenter config after registration."""
        config = module_registry.get("callcenter")
        assert config is not None
        assert config.department_id == "callcenter"

    @pytest.mark.unit
    def test_registry_can_get_marketing(self) -> None:
        """Registry should return marketing config after registration."""
        config = module_registry.get("marketing")
        assert config is not None
        assert config.department_id == "marketing"

    @pytest.mark.unit
    def test_registry_can_get_hr(self) -> None:
        """Registry should return hr config after registration."""
        config = module_registry.get("hr")
        assert config is not None
        assert config.department_id == "hr"

    @pytest.mark.unit
    def test_registry_rag_modules_returns_list(self) -> None:
        """Registry.rag_modules should return list of RAG configs."""
        rag_modules = module_registry.rag_modules()
        assert len(rag_modules) >= 3

        for config in rag_modules:
            assert config.module_type == ModuleType.RAG
