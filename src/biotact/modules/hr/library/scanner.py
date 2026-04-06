"""Scan DOCX templates for {{ PLACEHOLDER }} fields."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

PLACEHOLDER_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def scan_template_fields(file_path: str) -> list[str]:
    """Extract list of {{ PLACEHOLDER }} names from a DOCX template.

    Uses docxtpl to parse the template XML and find all Jinja2 variables.
    Falls back to regex scan if docxtpl method fails.
    """
    try:
        from docxtpl import DocxTemplate

        doc = DocxTemplate(file_path)
        fields = sorted(doc.get_undeclared_template_variables())
        if fields:
            logger.info("Scanned %d fields from %s: %s", len(fields), file_path, fields)
            return fields
    except Exception:
        logger.warning("docxtpl scan failed for %s, trying regex", file_path)

    # Fallback: regex on raw XML
    try:
        from docx import Document

        doc_raw = Document(file_path)
        all_text = "\n".join(p.text for p in doc_raw.paragraphs)
        # Also check tables
        for table in doc_raw.tables:
            for row in table.rows:
                for cell in row.cells:
                    all_text += "\n" + cell.text
        fields = sorted(set(PLACEHOLDER_RE.findall(all_text)))
        logger.info("Regex scanned %d fields from %s", len(fields), file_path)
        return fields
    except Exception:
        logger.exception("Failed to scan template fields from %s", file_path)
        return []
