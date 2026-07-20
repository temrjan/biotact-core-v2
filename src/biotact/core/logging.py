"""Application logging configuration.

Without an explicit handler the app's ``biotact.*`` loggers fall through to
``logging.lastResort`` (WARNING+), so ``logger.info(...)`` diagnostics never
appear in ``docker logs`` — the HR chat's whole INFO trail was invisible in
prod. This wires INFO to stdout.

Scope is deliberately ``biotact.modules.hr``, not the whole ``biotact`` tree:
enabling INFO app-wide would also surface PII-carrying INFO logs in un-audited
modules (e.g. ``documents/chat_service.py`` logs full tool-call args). Broaden
only after a per-module PII audit. See
``.claude/specs/2026-07-20-hr-pr-a-prompt-rules-logging.md``.
"""

from __future__ import annotations

import logging
import os
import sys

_HR_LOGGER_NAME = "biotact.modules.hr"
_HANDLER_NAME = "biotact-hr-stdout"
_DEFAULT_LEVEL = "INFO"


def _resolve_level(name: str) -> int:
    """Map a level name to its int value, falling back to INFO if unknown."""
    level = logging.getLevelName(name.upper())
    return level if isinstance(level, int) else logging.INFO


def configure_logging() -> None:
    """Send ``biotact.modules.hr`` INFO logs to stdout (idempotent).

    Level is read from ``LOG_LEVEL`` (default ``INFO``). Safe to call more than
    once — the stdout handler is added only when absent.
    """
    logger = logging.getLogger(_HR_LOGGER_NAME)
    logger.setLevel(_resolve_level(os.getenv("LOG_LEVEL", _DEFAULT_LEVEL)))

    if any(handler.get_name() == _HANDLER_NAME for handler in logger.handlers):
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.set_name(_HANDLER_NAME)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logger.addHandler(handler)
    # Our handler already emits to stdout; don't also bubble to the root logger.
    logger.propagate = False
