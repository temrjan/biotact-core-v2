"""Shared fixtures for the HR unit tests."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator


class _ListHandler(logging.Handler):
    """Capture fully-rendered log lines (message + any traceback)."""

    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


@pytest.fixture
def hr_log_lines() -> Iterator[list[str]]:
    """Capture ``biotact.modules.hr.*`` INFO+ lines regardless of propagation.

    Attaching to the package logger rather than using ``caplog`` keeps the
    capture working even though ``configure_logging`` sets ``propagate = False``.
    """
    handler = _ListHandler()
    logger = logging.getLogger("biotact.modules.hr")
    prev_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        yield handler.lines
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev_level)
