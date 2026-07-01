"""Render DOCX templates with data using docxtpl.

After rendering we normalize every table's widths so MS Word never draws a
table wider than the page (the "поплывшие ячейки" bug): bilingual HR templates
are laid out as tables whose grids are either autofit (Word sizes them from
content) or corrupted (fractional widths, column sum > page). LibreOffice
silently clamps such tables, so the overflow is only visible in MS Word.

The fix lives in the render code (not the template files): a single place
covers both generation paths and every already-uploaded template without a
migration. See ``.claude/specs/2026-06-30-hr-docx-table-width-normalization.md``.
"""

from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING, Any

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docxtpl import DocxTemplate  # type: ignore[import-untyped]

if TYPE_CHECKING:
    from docx.document import Document as DocxDocument

logger = logging.getLogger(__name__)

# Schema order of ``<w:tblPr>`` children (CT_TblPrBase). ``<w:tblW>`` must come
# before any of these, so we insert it *before* the first one that is present.
_TBLW_SUCCESSORS = (
    "w:jc",
    "w:tblCellSpacing",
    "w:tblInd",
    "w:tblBorders",
    "w:shd",
    "w:tblLayout",
    "w:tblCellMar",
    "w:tblLook",
    "w:tblCaption",
    "w:tblDescription",
)


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

    # Normalize on the rendered tree. We use ``doc.docx`` directly, NOT
    # ``doc.get_docx()``: the latter calls ``init_docx(reload=True)`` which,
    # once ``is_rendered`` is set, reloads the template from disk and discards
    # the render (verified on docxtpl 0.20.2).
    _normalize_table_widths(doc.docx)

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    logger.info("Rendered template %s with %d fields", template_path, len(context))
    return buffer


def _text_width_twips(document: DocxDocument) -> int | None:
    """Return the narrowest section's usable text width in twips.

    Text width = ``page_width - left_margin - right_margin`` for a section.
    Sections missing any of those measures are skipped.

    Returns:
        The minimum text width across valid sections, or ``None`` if no
        section provides all three measures.
    """
    widths: list[int] = []
    for section in document.sections:
        page_width = section.page_width
        left = section.left_margin
        right = section.right_margin
        if page_width is None or left is None or right is None:
            continue
        widths.append(page_width.twips - left.twips - right.twips)
    return min(widths) if widths else None


def _normalize_table_widths(document: DocxDocument) -> None:
    """Normalize every table so it never overflows its page width in MS Word.

    Iterates all tables (including nested ones) and, per table, rounds widths
    to integers, forces a fixed layout, and shrinks over-wide grids to the page
    while preserving column proportions. Fail-soft: any error is logged and the
    document is returned unchanged.
    """
    try:
        text_width = _text_width_twips(document)
        body = document.element.body
        for table in body.findall(".//" + qn("w:tbl")):
            _normalize_one_table(table, text_width)
    except Exception:
        logger.exception("Table width normalization failed; returning document as-is")


def _normalize_one_table(table: Any, text_width: int | None) -> None:
    """Normalize a single ``<w:tbl>`` element in place.

    Args:
        table: A ``w:tbl`` oxml element.
        text_width: Page text width in twips, or ``None`` if unavailable.
    """
    # Round every width to an integer first — layout-neutral, and it keeps the
    # "no fractional widths" guarantee even when the fallbacks below skip scaling.
    _round_widths(table)

    grid = table.find(qn("w:tblGrid"))
    cols = grid.findall(qn("w:gridCol")) if grid is not None else []
    # Reuse _round_width so a column with a missing or non-numeric width (e.g. a
    # universal measure like "1in") degrades to 0 instead of raising.
    widths = [_round_width(col.get(qn("w:w"))) or 0 for col in cols]
    grid_sum = sum(widths)

    # No clamp target or empty grid: round only, and leave the layout mode
    # untouched. Forcing a fixed layout here would strip Word/LibreOffice's
    # auto-clamp from a table that is not actually overflowing.
    if text_width is None or not cols or grid_sum <= 0:
        return

    max_width = text_width - _read_tblind(table)
    if max_width <= 0:
        max_width = text_width

    new_widths = _scale_down(widths, max_width) if grid_sum > max_width else widths
    for col, width in zip(cols, new_widths, strict=True):
        col.set(qn("w:w"), str(width))

    _force_fixed_layout(table)
    _set_table_width(table, sum(new_widths))
    _apply_cell_widths(table, new_widths)


def _round_widths(table: Any) -> None:
    """Round every ``w:w`` attribute under the table to an integer twip value."""
    for element in table.iter():
        rounded = _round_width(element.get(qn("w:w")))
        if rounded is not None:
            element.set(qn("w:w"), str(rounded))


def _round_width(value: str | None) -> int | None:
    """Round a raw OOXML width string to an int, or ``None`` if not numeric."""
    if value is None:
        return None
    try:
        return round(float(value))
    except ValueError:
        return None


def _read_tblind(table: Any) -> int:
    """Return the table indent (``w:tblInd``) in twips, or 0 if absent."""
    tbl_pr = table.find(qn("w:tblPr"))
    if tbl_pr is None:
        return 0
    tbl_ind = tbl_pr.find(qn("w:tblInd"))
    if tbl_ind is None:
        return 0
    return _round_width(tbl_ind.get(qn("w:w"))) or 0


def _scale_down(widths: list[int], target: int) -> list[int]:
    """Scale column widths down to ``target`` twips, preserving proportions.

    Each column becomes ``round(width * target / total)``; the integer rounding
    remainder is spread one twip at a time so the columns sum to exactly
    ``target``.
    """
    total = sum(widths)
    factor = target / total
    scaled = [max(1, round(width * factor)) for width in widths]

    diff = target - sum(scaled)
    index = 0
    guard = 0
    while diff != 0 and guard < 10_000:
        position = index % len(scaled)
        if diff > 0:
            scaled[position] += 1
            diff -= 1
        elif scaled[position] > 1:
            scaled[position] -= 1
            diff += 1
        index += 1
        guard += 1
    return scaled


def _force_fixed_layout(table: Any) -> None:
    """Force ``<w:tblLayout w:type="fixed"/>`` on the table."""
    tbl_pr = _get_or_add_tbl_pr(table)
    tbl_pr.get_or_add_tblLayout().set(qn("w:type"), "fixed")


def _set_table_width(table: Any, width: int) -> None:
    """Set the table's total preferred width (``<w:tblW>``) to ``width`` dxa."""
    tbl_pr = _get_or_add_tbl_pr(table)
    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.insert_element_before(tbl_w, *_TBLW_SUCCESSORS)
    tbl_w.set(qn("w:w"), str(width))
    tbl_w.set(qn("w:type"), "dxa")


def _apply_cell_widths(table: Any, col_widths: list[int]) -> None:
    """Recompute each cell's ``<w:tcW>`` from the normalized column widths.

    Cells are walked left-to-right per row; a cell with ``gridSpan=n`` gets the
    sum of the ``n`` columns it covers.
    """
    col_count = len(col_widths)
    for row in table.findall(qn("w:tr")):
        cursor = 0
        for cell in row.findall(qn("w:tc")):
            span = _grid_span(cell)
            end = min(cursor + span, col_count)
            width = sum(col_widths[cursor:end]) if cursor < col_count else 0
            tc_w = cell.get_or_add_tcPr().get_or_add_tcW()
            tc_w.set(qn("w:w"), str(width))
            tc_w.set(qn("w:type"), "dxa")
            cursor += span


def _grid_span(cell: Any) -> int:
    """Return the cell's horizontal span (``w:gridSpan``), defaulting to 1."""
    tc_pr = cell.find(qn("w:tcPr"))
    if tc_pr is None:
        return 1
    grid_span = tc_pr.find(qn("w:gridSpan"))
    if grid_span is None:
        return 1
    value = grid_span.get(qn("w:val"))
    if value is None:
        return 1
    try:
        return max(1, int(value))
    except ValueError:
        return 1


def _get_or_add_tbl_pr(table: Any) -> Any:
    """Return the table's ``<w:tblPr>``, creating it as the first child if absent."""
    tbl_pr = table.find(qn("w:tblPr"))
    if tbl_pr is None:
        tbl_pr = OxmlElement("w:tblPr")
        table.insert(0, tbl_pr)
    return tbl_pr
