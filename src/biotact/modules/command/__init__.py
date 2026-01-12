"""Command-based modules for BIOTACT.

Command modules use Function Calling to parse user intent
and execute actions on PostgreSQL.
"""

from biotact.modules.command.base import BaseCommandService

__all__ = ["BaseCommandService"]
