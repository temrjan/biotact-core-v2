"""The upload picker may only offer categories the backend has rules for.

The dashboard's category `<select>` decides what a freshly uploaded template is
filed under, and that key is what `build_extractor_rules` looks up. A key the
backend does not know degrades silently: extraction falls back to the common
rules (`field_rules.py`), the document loses its own — order number, position in
the genitive case, date in words — and it still renders, just worse.

Eight of the ten original options were outside the canonical set. Nothing caught
it because the dashboard has no test harness of its own (`package.json` carries
only eslint and vite), so this contract is pinned from the Python side: it is
the only place where both ends of it are visible at once.
"""

from __future__ import annotations

import re
from pathlib import Path

from biotact.modules.hr.chat.categories import POSTPROCESS_BY_CATEGORY

_DASHBOARD = (
    Path(__file__).resolve().parents[3]
    / "frontend"
    / "dashboard"
    / "src"
    / "BiotactDashboard.jsx"
)
# Anchored on the state binding, not on the file: the dashboard holds unrelated
# <select> elements (TTS voices, for one), and sweeping the whole file would
# measure those too.
_PICKER_BLOCK = re.compile(r"value=\{hrSelectedCategory\}(.*?)</select>", re.S)
_OPTION_VALUE = re.compile(r'<option value="([^"]+)"')


def _picker_categories() -> list[str]:
    """Category keys the upload picker offers, in source order."""
    block = _PICKER_BLOCK.search(_DASHBOARD.read_text(encoding="utf-8"))
    if block is None:
        return []
    return _OPTION_VALUE.findall(block.group(1))


def test_the_picker_is_where_we_think_it_is() -> None:
    """Guard the guard: renamed state or moved file must fail loudly.

    Without this, every assertion below would pass vacuously on an empty list.
    """
    assert _DASHBOARD.is_file(), _DASHBOARD
    assert _picker_categories(), "upload picker not found — did the markup change?"


def test_every_offered_category_has_backend_rules() -> None:
    unknown = [c for c in _picker_categories() if c not in POSTPROCESS_BY_CATEGORY]
    assert unknown == []


def test_picker_offers_every_supported_category() -> None:
    """The other direction: a supported category HR cannot pick is dead weight."""
    missing = sorted(set(POSTPROCESS_BY_CATEGORY) - set(_picker_categories()))
    assert missing == []
