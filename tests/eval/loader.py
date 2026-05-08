"""Gold-set loader for AskBiotact evaluation.

Reads ``tests/eval/biotact_gold_set.jsonl`` into typed dataclasses.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Category = Literal[
    "price", "composition", "symptoms", "follow_up", "multi_product", "safety"
]
Lang = Literal["ru", "uz"]

# Runtime guards — Literal[...] is type-only; we enforce membership at load
# so SME typos in the JSONL (e.g. "saftey") fail fast rather than aggregating
# into the wrong bucket silently.
_VALID_CATEGORIES: frozenset[str] = frozenset(
    ["price", "composition", "symptoms", "follow_up", "multi_product", "safety"]
)
_VALID_LANGS: frozenset[str] = frozenset(["ru", "uz"])


@dataclass(frozen=True, slots=True)
class ExpectedAnswerTraits:
    """What the bot's answer must (or must not) contain."""

    must_mention: list[str] = field(default_factory=list)
    must_not_mention: list[str] = field(default_factory=list)
    should_redirect_to_doctor: bool = False


@dataclass(frozen=True, slots=True)
class GoldCase:
    """One evaluation dialog from the gold set."""

    id: str
    category: Category
    lang: Lang
    dialog: list[dict[str, str]]
    expected_chunk_substrings: list[str]
    expected_answer_traits: ExpectedAnswerTraits
    sme_validated_by: str | None = None
    sme_validated_at: str | None = None
    notes: str = ""

    @property
    def last_user_message(self) -> str:
        for msg in reversed(self.dialog):
            if msg.get("role") == "user":
                return msg["content"]
        raise ValueError(f"GoldCase {self.id} has no user message")

    @property
    def seeded_history(self) -> list[dict[str, str]]:
        """Messages BEFORE the last user turn — mimics Redis chat history."""
        last_user_idx: int | None = None
        for i in range(len(self.dialog) - 1, -1, -1):
            if self.dialog[i].get("role") == "user":
                last_user_idx = i
                break
        if last_user_idx is None:
            return []
        return list(self.dialog[:last_user_idx])


def load_gold_set(path: str | Path) -> list[GoldCase]:
    """Load JSONL gold set, validate each record, return typed cases.

    Raises:
        ValueError: if a record is malformed or missing a required field.
    """
    cases: list[GoldCase] = []
    p = Path(path)
    with p.open(encoding="utf-8") as f:
        for line_num, raw_line in enumerate(f, start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
            except json.JSONDecodeError as e:
                raise ValueError(f"{p}:{line_num} invalid JSON: {e}") from e

            traits_raw = data.get("expected_answer_traits", {})
            traits = ExpectedAnswerTraits(
                must_mention=list(traits_raw.get("must_mention", [])),
                must_not_mention=list(traits_raw.get("must_not_mention", [])),
                should_redirect_to_doctor=bool(
                    traits_raw.get("should_redirect_to_doctor", False)
                ),
            )

            try:
                category = data["category"]
                lang = data["lang"]
            except KeyError as e:
                raise ValueError(f"{p}:{line_num} missing field {e}") from e

            if category not in _VALID_CATEGORIES:
                raise ValueError(
                    f"{p}:{line_num} unknown category {category!r} "
                    f"(valid: {sorted(_VALID_CATEGORIES)})"
                )
            if lang not in _VALID_LANGS:
                raise ValueError(
                    f"{p}:{line_num} unknown lang {lang!r} "
                    f"(valid: {sorted(_VALID_LANGS)})"
                )

            try:
                case = GoldCase(
                    id=data["id"],
                    category=category,
                    lang=lang,
                    dialog=list(data["dialog"]),
                    expected_chunk_substrings=list(
                        data.get("expected_chunk_substrings", [])
                    ),
                    expected_answer_traits=traits,
                    sme_validated_by=data.get("sme_validated_by"),
                    sme_validated_at=data.get("sme_validated_at"),
                    notes=data.get("notes", ""),
                )
            except KeyError as e:
                raise ValueError(f"{p}:{line_num} missing field {e}") from e

            cases.append(case)
    return cases
