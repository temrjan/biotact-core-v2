"""Base module configuration for BIOTACT departments.

This module defines the base configuration classes for department modules.
There are two types of modules:
- Command-based (Dashboard): LLM parses intent → Function Call → SQL action
- RAG-based (CallCenter, Marketing, HR): Search knowledge base → Generate response
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ModuleType(StrEnum):
    """Type of module processing."""

    COMMAND = "command"  # Function Calling → SQL actions
    RAG = "rag"  # Vector search → LLM generation


@dataclass
class BaseModuleConfig(ABC):
    """Base configuration for all department modules.

    Attributes:
        department_id: Unique identifier for the department.
        display_name: Human-readable name for UI.
        description: Short description of the module.
        module_type: Processing type (COMMAND or RAG).
        system_prompt: System message for LLM.
        is_active: Whether the module is enabled.
    """

    department_id: str
    display_name: str
    description: str
    module_type: ModuleType
    system_prompt: str
    is_active: bool = True

    @abstractmethod
    def get_system_message(self, context: dict[str, Any] | None = None) -> str:
        """Build the system message for LLM.

        Args:
            context: Optional context data to include in the prompt.

        Returns:
            Formatted system message string.
        """
        pass


@dataclass
class CommandModuleConfig(BaseModuleConfig):
    """Configuration for command-based modules (e.g., Dashboard).

    Command modules use Function Calling to parse user intent
    and execute actions (INSERT, SELECT, UPDATE) on PostgreSQL.

    Attributes:
        tools: List of Function Calling tool definitions.
        max_clarification_turns: Max turns for multi-turn clarification.
    """

    module_type: ModuleType = field(default=ModuleType.COMMAND, init=False)
    tools: list[dict[str, Any]] = field(default_factory=list)
    max_clarification_turns: int = 3

    def get_system_message(self, context: dict[str, Any] | None = None) -> str:
        """Build system message for command-based module."""
        base_prompt = self.system_prompt

        if context:
            # Add context like available categories, current date, etc.
            if "categories" in context:
                categories_str = ", ".join(context["categories"])
                base_prompt += f"\n\nДоступные категории: {categories_str}"

            if "current_date" in context:
                base_prompt += f"\n\nТекущая дата: {context['current_date']}"

        return base_prompt


@dataclass
class RAGModuleConfig(BaseModuleConfig):
    """Configuration for RAG-based modules (e.g., CallCenter, Marketing, HR).

    RAG modules search the Qdrant knowledge base filtered by department
    and generate responses based on retrieved context.

    Attributes:
        rag_limit: Maximum number of search results.
        score_threshold: Minimum similarity score for results.
        department_filter: Qdrant payload filter value for this department.
    """

    module_type: ModuleType = field(default=ModuleType.RAG, init=False)
    rag_limit: int = 5
    score_threshold: float = 0.3
    department_filter: str | None = None  # If None, uses department_id

    def __post_init__(self) -> None:
        """Set department_filter to department_id if not specified."""
        if self.department_filter is None:
            self.department_filter = self.department_id

    def get_system_message(self, context: dict[str, Any] | None = None) -> str:
        """Build system message for RAG-based module."""
        base_prompt = self.system_prompt

        if context and "retrieved_docs" in context:
            # Add retrieved documents summary
            docs_count = len(context["retrieved_docs"])
            base_prompt += (
                f"\n\nИспользуй {docs_count} найденных документов для ответа."
            )

        return base_prompt
