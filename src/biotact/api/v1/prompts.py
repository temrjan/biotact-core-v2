"""Prompts API endpoints."""

import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from biotact.core.dependencies import CurrentUserDep, get_current_user

router = APIRouter(
    prefix="/prompts", tags=["prompts"], dependencies=[Depends(get_current_user)]
)

PROMPTS_DIR = Path(__file__).parent.parent.parent.parent.parent / "prompts"


class PromptResponse(BaseModel):
    """Prompt response schema."""

    name: str
    content: str


class PromptUpdateRequest(BaseModel):
    """Prompt update request schema."""

    content: str


@router.get("/{name}", response_model=PromptResponse)
async def get_prompt(name: str) -> PromptResponse:
    """Get prompt content by name."""
    # Sanitize name to prevent path traversal
    safe_name = name.replace("..", "").replace("/", "").replace("\\", "")
    prompt_path = PROMPTS_DIR / f"{safe_name}.txt"

    if not prompt_path.exists():
        raise HTTPException(status_code=404, detail=f"Prompt '{name}' not found")

    try:
        content = prompt_path.read_text(encoding="utf-8")
        return PromptResponse(name=safe_name, content=content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.put("/{name}", response_model=PromptResponse)
async def update_prompt(
    name: str, request: PromptUpdateRequest, current_user: CurrentUserDep
) -> PromptResponse:
    """Update prompt content with automatic backup."""
    if current_user.department_id != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    safe_name = name.replace("..", "").replace("/", "").replace("\\", "")
    prompt_path = PROMPTS_DIR / f"{safe_name}.txt"

    if not prompt_path.exists():
        raise HTTPException(status_code=404, detail=f"Prompt '{name}' not found")

    try:
        # Create backup before overwriting
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = PROMPTS_DIR / f"{safe_name}_backup_{timestamp}.txt"
        shutil.copy2(prompt_path, backup_path)

        # Write new content
        prompt_path.write_text(request.content, encoding="utf-8")
        return PromptResponse(name=safe_name, content=request.content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/", response_model=list[PromptResponse])
async def list_prompts() -> list[PromptResponse]:
    """List all available prompts."""
    prompts = []
    if PROMPTS_DIR.exists():
        for file in PROMPTS_DIR.glob("*.txt"):
            if not file.name.endswith("_backup.txt"):
                prompts.append(
                    PromptResponse(
                        name=file.stem,
                        content=file.read_text(encoding="utf-8")[:200] + "...",
                    )
                )
    return prompts
