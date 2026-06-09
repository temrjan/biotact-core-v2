"""API v1 endpoints."""

from fastapi import APIRouter

from biotact.api.v1.auth import router as auth_router
from biotact.api.v1.chat import router as chat_router
from biotact.api.v1.dashboard import router as dashboard_router
from biotact.api.v1.health import router as health_router
from biotact.api.v1.hr_digest import router as hr_digest_router
from biotact.api.v1.knowledge import router as knowledge_router
from biotact.api.v1.marketing import router as marketing_router
from biotact.api.v1.prompts import router as prompts_router
from biotact.api.v1.public import router as public_router
from biotact.api.v1.webhooks import router as webhooks_router
from biotact.modules.crm.router import router as crm_router
from biotact.modules.documents.router import router as documents_router
from biotact.modules.hr.chat.router import router as hr_chat_router
from biotact.modules.hr.documents.router import router as hr_documents_router
from biotact.modules.hr.events.router import router as hr_events_router
from biotact.modules.hr.gifts.router import router as hr_gifts_router
from biotact.modules.hr.library.router import router as hr_library_router
from biotact.modules.media.router import router as media_router

router = APIRouter(prefix="/api/v1")
router.include_router(health_router)
router.include_router(auth_router)
router.include_router(chat_router)
router.include_router(dashboard_router)
router.include_router(prompts_router)
router.include_router(hr_digest_router)
router.include_router(public_router)
router.include_router(webhooks_router)
router.include_router(crm_router)
router.include_router(marketing_router)
router.include_router(documents_router)
router.include_router(hr_library_router)
router.include_router(hr_chat_router)
router.include_router(hr_documents_router)
router.include_router(hr_gifts_router)
router.include_router(hr_events_router)
router.include_router(knowledge_router)
router.include_router(media_router)

__all__ = ["router"]
