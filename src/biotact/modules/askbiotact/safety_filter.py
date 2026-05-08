"""Code-level safety guard for AskBiotact (Phase 0.6).

Insurance over the Phase 0.5 prompt-level safety rules. Detects safety
triggers in the user message and post-processes the Pilot's answer to:

  1. Strip BIOTACT product names from answers in safety contexts
  2. Ensure a redirect to the appropriate specialist is present

This is a *defensive* layer: it cannot make the bot answer worse, but
it removes the residual risk that Pilot bypasses the prompt rules
(LLM drift, future model upgrades, jailbreak attempts).
"""

from __future__ import annotations

import re

from biotact.modules.askbiotact.constants import PRODUCT_NAMES

# =============================================================================
# Trigger detection
# =============================================================================

_PREGNANCY = re.compile(
    r"\b(беремен|кормл[юяе]|кормить грудь|грудью|homilador|emiz(?:ish|adigan|gan))",
    re.IGNORECASE,
)

_CHILD_KEYWORDS = re.compile(
    r"\b(дочь|дочер|сын|реб[её]н|малыш|младенц|новорожд|bola|farzand)\w*",
    re.IGNORECASE,
)
_YOUNG_AGE_KEYWORDS = re.compile(
    r"\b("
    r"новорожд"
    r"|(?:1|2|3)\s*(?:год|года|годик|годика|месяц|oy|yosh)"
    r"|(?:годик|пол\s*года|полтора\s*года|год\b)"
    r"|(?:1[0-9]|2[0-9]|3[0-5])\s*(?:месяц|oy)"
    r")",
    re.IGNORECASE,
)

_CARDIAC = re.compile(
    r"\b(серд[цеоьаы]|кардио|yur(?:ak|ag)\w*|одышк|задыха)",
    re.IGNORECASE,
)

_CHRONIC = re.compile(
    r"\b("
    r"диабет|qandli|sahar\s*kasal"
    r"|гипертон|gipert"
    r"|онколог|рак\b|онко\b"
    r"|surunkali|chronic"
    r")",
    re.IGNORECASE,
)


def detect_safety_trigger(user_message: str) -> str | None:
    """Return trigger category, or None if message is safe.

    Priority: pregnancy → child_under_3 → cardiac → chronic.
    First match wins (a pregnant woman with diabetes is still pregnancy).
    """
    if _PREGNANCY.search(user_message):
        return "pregnancy"
    if _CHILD_KEYWORDS.search(user_message) and _YOUNG_AGE_KEYWORDS.search(
        user_message
    ):
        return "child_under_3"
    if _CARDIAC.search(user_message):
        return "cardiac"
    if _CHRONIC.search(user_message):
        return "chronic"
    return None


# =============================================================================
# Post-filter
# =============================================================================

# Full + base product names — sorted by length descending so multi-word names
# match before their leading word ("BIFOLAK NEO" before "BIFOLAK").
_PRODUCT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(rf"\b{re.escape(name)}\b", re.IGNORECASE)
    for name in sorted(
        set(PRODUCT_NAMES) | {p.split()[0] for p in PRODUCT_NAMES},
        key=len,
        reverse=True,
    )
)

_DOCTOR_TERMS = (
    "врач",
    "доктор",
    "педиатр",
    "кардиолог",
    "гинеколог",
    "терапевт",
    "shifokor",
    "kardiolog",
    "ginekolog",
    "pediatr",
    "vrach",
    "doctor",
)

_SPECIALIST_RU: dict[str, str] = {
    "pregnancy": "гинекологу",
    "child_under_3": "педиатру",
    "cardiac": "кардиологу",
    "chronic": "лечащему врачу",
}

_SPECIALIST_UZ: dict[str, str] = {
    "pregnancy": "ginekologga",
    "child_under_3": "pediatrga",
    "cardiac": "kardiologga",
    "chronic": "davolovchi shifokoringizga",
}


def _is_uz(text: str) -> bool:
    """Heuristic language detector — UZ uses Latin + UZ-specific tokens."""
    lowered = text.lower()
    uz_markers = (
        "shifokor",
        "narx",
        "yosh",
        "homilador",
        "yurak",
        "qancha",
        "qandli",
        "tarkibi",
        "bola",
        "ichsam",
        "ichish",
        "ginekolog",
    )
    return any(m in lowered for m in uz_markers)


def _has_doctor_mention(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in _DOCTOR_TERMS)


def _strip_product_names(text: str, placeholder: str) -> str:
    """Replace any BIOTACT product name occurrence with the given placeholder.

    Idempotent: subsequent calls find no matches.
    """
    cleaned = text
    for pattern in _PRODUCT_PATTERNS:
        cleaned = pattern.sub(placeholder, cleaned)
    return cleaned


def apply_safety_filter(
    answer: str,
    user_message: str,
    trigger: str,
) -> str:
    """Strip product names and ensure a doctor redirect is present.

    Language is decided by the user's message (source of truth) — if user
    wrote UZ we redirect in UZ even if Pilot answered in RU.

    Idempotent: ``apply(apply(x, msg, t), msg, t) == apply(x, msg, t)``.
    """
    is_uz = _is_uz(user_message)
    placeholder = "[shifokor bilan kelishing]" if is_uz else "[обсудите с врачом]"
    cleaned = _strip_product_names(answer, placeholder)

    if not _has_doctor_mention(cleaned):
        if is_uz:
            specialist = _SPECIALIST_UZ.get(trigger, "davolovchi shifokoringizga")
            cleaned = f"{cleaned}\n\nIltimos, {specialist} murojaat qiling."
        else:
            specialist = _SPECIALIST_RU.get(trigger, "лечащему врачу")
            cleaned = f"{cleaned}\n\nПожалуйста, обратитесь к {specialist}."

    return cleaned
