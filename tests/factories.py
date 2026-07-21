"""Shared test factories."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

from docx import Document

if TYPE_CHECKING:
    from collections.abc import Sequence


def make_docx_bytes(fields: Sequence[str] = ()) -> bytes:
    """Build a real, openable ``.docx`` with one ``{{ FIELD }}`` paragraph per field.

    Replaces the fake ``b"PK..."`` payloads: the upload path now rejects DOCX that
    python-docx cannot open, so tests must use a genuine document.
    """
    doc = Document()
    for name in fields:
        doc.add_paragraph(f"{{{{ {name} }}}}")
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
