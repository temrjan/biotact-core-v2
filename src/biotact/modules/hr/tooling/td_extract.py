"""Extract the current TD template's clauses into a Markdown checklist.

The author rebuilds the ``.docx`` in Word against this checklist (the source of
truth is the original template on the server). Columns are shown side by side
BY POSITION only — the two languages do not align 1:1 (different clause counts),
so real pairing is a human/legal decision; gaps are flagged, never silently
aligned. Run: ``python -m biotact.modules.hr.tooling.td_extract ORIG [--out F]``.
"""

from __future__ import annotations

import argparse

from docx import Document

from biotact.modules.hr.tooling.docx_text import extract_columns


def _md_cell(text: str) -> str:
    """Escape a value for a Markdown table cell."""
    return text.replace("|", "\\|").replace("\n", " ")


def to_markdown(uz: list[str], ru: list[str]) -> str:
    """Render the side-by-side checklist with gap flags."""
    lines = [
        "# Трудовой договор — экстракт пунктов (источник истины для авторинга)",
        "",
        f"- UZ пунктов: {len(uz)}",
        f"- RU пунктов: {len(ru)}",
        "",
        "> Колонка «поз.» — соседство ПО ПОЗИЦИИ, НЕ подтверждённое спаривание.",
        "> `GAP-*` = в этой позиции у одной стороны пусто. Реальное спаривание "
        "UZ↔RU и разбор дырок — решение человека (юр-вопрос).",
        "",
    ]
    if len(uz) != len(ru):
        lines.append(
            f"> ⚠️ Колонки НЕ совпадают по числу пунктов (Δ={abs(len(uz) - len(ru))})."
        )
        lines.append("")
    lines += ["| # | поз. | UZ | RU |", "|---|---|---|---|"]
    for index in range(max(len(uz), len(ru))):
        uz_text = uz[index] if index < len(uz) else ""
        ru_text = ru[index] if index < len(ru) else ""
        if uz_text and ru_text:
            flag = "✓"
        elif uz_text:
            flag = "GAP-RU"
        else:
            flag = "GAP-UZ"
        lines.append(
            f"| {index} | {flag} | {_md_cell(uz_text)} | {_md_cell(ru_text)} |"
        )
    return "\n".join(lines) + "\n"


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", help="path to the current template .docx")
    parser.add_argument("--out", help="write Markdown here (default: stdout)")
    args = parser.parse_args(argv)

    uz, ru = extract_columns(Document(args.original))
    markdown = to_markdown(uz, ru)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(markdown)
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
