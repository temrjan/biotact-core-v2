"""Render DOCX templates with data using docxtpl."""

from __future__ import annotations

import io
import logging

from docxtpl import DocxTemplate

logger = logging.getLogger(__name__)


def render_template(template_path: str, context: dict[str, str]) -> io.BytesIO:
    """Render a DOCX template by replacing {{ PLACEHOLDERS }} with context data.

    Args:
        template_path: Path to the DOCX template file.
        context: Dict mapping placeholder names to values.

    Returns:
        BytesIO buffer with the rendered DOCX.
    """
    doc = DocxTemplate(template_path)
    doc.render(context)

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    logger.info("Rendered template %s with %d fields", template_path, len(context))
    return buffer
