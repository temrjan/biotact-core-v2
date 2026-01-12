"""Command executor service for Function Calling.

This service handles LLM interactions for command-based modules:
1. Sends user message to LLM with tools defined by the module
2. Parses Function Calling response
3. Delegates tool execution to module service
4. Handles multi-turn clarification flow
"""

import json
import logging
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageToolCall

from biotact.core.config import Settings
from biotact.modules.base import CommandModuleConfig
from biotact.modules.command.base import CommandResult, ToolCall

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Result of command execution flow.

    Attributes:
        response: Text response to send to user.
        tool_calls: List of tool calls made (for logging/debugging).
        action_result: Result data from executed action.
        needs_clarification: Whether more info needed from user.
    """

    response: str
    tool_calls: list[ToolCall]
    action_result: dict[str, Any] | None = None
    needs_clarification: bool = False


class CommandExecutor:
    """Executes commands through LLM Function Calling.

    This service:
    1. Builds messages with system prompt and tools from module config
    2. Calls OpenAI with Function Calling enabled
    3. Parses tool calls from response
    4. Returns parsed calls for module service to execute

    The actual tool execution is delegated to the module's service
    (e.g., DashboardService) which knows how to handle each tool.
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize command executor.

        Args:
            settings: Application settings with OpenAI credentials.
        """
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model

    async def process_message(
        self,
        message: str,
        config: CommandModuleConfig,
        chat_history: list[dict[str, str]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> tuple[list[ToolCall], str | None]:
        """Process user message and extract tool calls.

        Args:
            message: User's message.
            config: Module configuration with tools and prompt.
            chat_history: Previous messages for context.
            context: Additional context for system prompt.

        Returns:
            Tuple of (list of tool calls, optional text response).
            If no tool calls, text response contains LLM's message.
        """
        # Build system prompt
        system_prompt = config.get_system_message(context)

        # Build messages
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]

        # Add chat history
        if chat_history:
            messages.extend(chat_history[-10:])

        # Add current message
        messages.append({"role": "user", "content": message})

        # Call OpenAI with tools
        try:
            response = await self.client.chat.completions.create(  # type: ignore[call-overload]
                model=self.model,
                messages=messages,
                tools=config.tools if config.tools else None,
                tool_choice="auto" if config.tools else None,
                max_tokens=500,
                temperature=0.3,
            )
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return [], f"Ошибка при обработке запроса: {e}"

        # Parse response
        choice = response.choices[0]
        assistant_message = choice.message

        # Check for tool calls
        if assistant_message.tool_calls:
            tool_calls = self._parse_tool_calls(assistant_message.tool_calls)
            return tool_calls, None

        # No tool calls - return text response
        return [], assistant_message.content

    def _parse_tool_calls(
        self,
        tool_calls: list[ChatCompletionMessageToolCall],
    ) -> list[ToolCall]:
        """Parse tool calls from OpenAI response.

        Args:
            tool_calls: Raw tool calls from API.

        Returns:
            List of parsed ToolCall objects.
        """
        parsed = []
        for tc in tool_calls:
            try:
                arguments = json.loads(tc.function.arguments)
                parsed.append(
                    ToolCall(
                        name=tc.function.name,
                        arguments=arguments,
                        raw_arguments=tc.function.arguments,
                    )
                )
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse tool arguments: {e}")
                parsed.append(
                    ToolCall(
                        name=tc.function.name,
                        arguments={},
                        raw_arguments=tc.function.arguments,
                    )
                )
        return parsed

    async def generate_tool_response(
        self,
        original_message: str,
        tool_call: ToolCall,
        tool_result: CommandResult,
        config: CommandModuleConfig,
    ) -> str:
        """Generate natural language response after tool execution.

        Args:
            original_message: User's original message.
            tool_call: The tool that was called.
            tool_result: Result from executing the tool.
            config: Module configuration.

        Returns:
            Natural language response to user.
        """
        # If result already has a good message, use it
        if tool_result.message and not tool_result.needs_clarification:
            return tool_result.message

        # Otherwise, ask LLM to format the response
        system_prompt = """Ты помощник, который форматирует результаты операций.
Сообщи пользователю о результате операции кратко и понятно.
Используй эмодзи ✓ для успеха и ✗ для ошибки."""

        result_json = json.dumps(
            {
                "success": tool_result.success,
                "data": tool_result.data,
                "action": tool_call.name,
            },
            ensure_ascii=False,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Запрос пользователя: {original_message}\n\nРезультат: {result_json}",
            },
        ]

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=200,
                temperature=0.3,
            )
            return response.choices[0].message.content or tool_result.message
        except Exception as e:
            logger.error(f"Failed to generate tool response: {e}")
            return tool_result.message

    async def request_clarification(
        self,
        original_message: str,
        missing_fields: list[str],
        _config: CommandModuleConfig,
    ) -> str:
        """Generate clarification request for missing parameters.

        Args:
            original_message: User's original message.
            missing_fields: List of required fields that are missing.
            config: Module configuration.

        Returns:
            Clarification question for user.
        """
        system_prompt = """Ты помощник, который уточняет недостающую информацию.
Задай один краткий уточняющий вопрос, чтобы получить недостающие данные.
Будь вежлив и конкретен."""

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Запрос: {original_message}\nНедостающие данные: {', '.join(missing_fields)}",
            },
        ]

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=100,
                temperature=0.5,
            )
            return response.choices[0].message.content or f"Уточните: {', '.join(missing_fields)}"
        except Exception as e:
            logger.error(f"Failed to generate clarification: {e}")
            return f"Пожалуйста, уточните: {', '.join(missing_fields)}"
