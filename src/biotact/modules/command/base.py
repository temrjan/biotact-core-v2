"""Base service for command-based modules.

Command modules handle user requests through Function Calling:
1. User sends natural language command
2. LLM parses intent and extracts parameters via Function Calling
3. Service executes the appropriate action (INSERT, SELECT, etc.)
4. Response is formatted and returned

Supports multi-turn clarification when required parameters are missing.
"""

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from biotact.modules.base import CommandModuleConfig

logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    """Represents a parsed tool call from LLM.

    Attributes:
        name: Tool/function name.
        arguments: Parsed arguments dictionary.
        raw_arguments: Original JSON string from LLM.
    """

    name: str
    arguments: dict[str, Any]
    raw_arguments: str


@dataclass
class CommandResult:
    """Result of executing a command.

    Attributes:
        success: Whether the command executed successfully.
        message: Human-readable response message.
        data: Optional data payload (e.g., created record, report).
        needs_clarification: Whether more info is needed from user.
        clarification_prompt: Question to ask user for clarification.
    """

    success: bool
    message: str
    data: dict[str, Any] | None = None
    needs_clarification: bool = False
    clarification_prompt: str | None = None


class BaseCommandService(ABC):
    """Base service for command-based department modules.

    Subclasses must implement:
    - execute_tool(): Execute specific tool by name
    - get_context(): Get context for system prompt

    Example:
        >>> class DashboardService(BaseCommandService):
        ...     async def execute_tool(self, tool_call: ToolCall) -> CommandResult:
        ...         if tool_call.name == "add_financial_record":
        ...             return await self._add_record(tool_call.arguments)
        ...         return CommandResult(success=False, message="Unknown tool")
    """

    def __init__(self, config: CommandModuleConfig) -> None:
        """Initialize command service.

        Args:
            config: Module configuration with tools and prompts.
        """
        self.config = config
        self._clarification_context: dict[str, Any] = {}

    @property
    def tools(self) -> list[dict[str, Any]]:
        """Get Function Calling tool definitions."""
        return self.config.tools

    @property
    def system_prompt(self) -> str:
        """Get system prompt with context."""
        context = self.get_context()
        return self.config.get_system_message(context)

    @abstractmethod
    def get_context(self) -> dict[str, Any]:
        """Get context data for system prompt.

        Returns:
            Dictionary with context like categories, current date, etc.
        """
        pass

    @abstractmethod
    async def execute_tool(self, tool_call: ToolCall) -> CommandResult:
        """Execute a specific tool by name.

        Args:
            tool_call: Parsed tool call from LLM.

        Returns:
            CommandResult with success/failure and message.
        """
        pass

    def parse_tool_call(self, tool_call_response: dict[str, Any]) -> ToolCall | None:
        """Parse tool call from OpenAI response.

        Args:
            tool_call_response: Raw tool call from OpenAI API.

        Returns:
            Parsed ToolCall or None if parsing fails.
        """
        try:
            function = tool_call_response.get("function", {})
            name = function.get("name", "")
            raw_args = function.get("arguments", "{}")

            # Parse JSON arguments
            try:
                arguments = json.loads(raw_args)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse tool arguments: {raw_args}")
                arguments = {}

            return ToolCall(name=name, arguments=arguments, raw_arguments=raw_args)

        except Exception as e:
            logger.error(f"Failed to parse tool call: {e}")
            return None

    async def handle_message(
        self,
        message: str,
        chat_history: list[dict[str, str]] | None = None,
    ) -> CommandResult:
        """Handle user message and return result.

        This is the main entry point for processing commands.
        Subclasses typically don't override this.

        Args:
            message: User's message.
            chat_history: Previous messages for context.

        Returns:
            CommandResult with response.
        """
        # This method will be implemented when we integrate with LLM
        # For now, return placeholder
        _ = message, chat_history  # Will be used in implementation
        return CommandResult(
            success=False,
            message="Command processing not yet implemented",
        )

    def set_clarification_context(self, context: dict[str, Any]) -> None:
        """Store context for multi-turn clarification.

        Args:
            context: Partial data collected so far.
        """
        self._clarification_context = context

    def get_clarification_context(self) -> dict[str, Any]:
        """Get stored clarification context."""
        return self._clarification_context

    def clear_clarification_context(self) -> None:
        """Clear clarification context after successful command."""
        self._clarification_context = {}

    def create_clarification_result(
        self,
        prompt: str,
        partial_data: dict[str, Any] | None = None,
    ) -> CommandResult:
        """Create a result requesting clarification from user.

        Args:
            prompt: Question to ask user.
            partial_data: Data collected so far to preserve.

        Returns:
            CommandResult with needs_clarification=True.
        """
        if partial_data:
            self.set_clarification_context(partial_data)

        return CommandResult(
            success=True,  # Not an error, just needs more info
            message=prompt,
            needs_clarification=True,
            clarification_prompt=prompt,
        )
