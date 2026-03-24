"""AskBiotact module configuration."""

from pathlib import Path

from biotact.modules.base import RAGModuleConfig


def _load_prompt() -> str:
    """Load system prompt from file."""
    prompt_path = (
        Path(__file__).parent.parent.parent.parent.parent / "prompts" / "askbiotact.txt"
    )
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    return ""


askbiotact_config = RAGModuleConfig(
    department_id="askbiotact",
    display_name="AskBiotact Telegram",
    description="Консультант по здоровью BIOTACT",
    system_prompt=_load_prompt(),
    rag_limit=10,
    score_threshold=0.30,
    department_filter="askbiotact",
)
