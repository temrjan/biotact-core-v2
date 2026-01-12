"""FastAPI application entrypoint."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from biotact import __version__
from biotact.api.v1 import router as api_router
from biotact.api.v1.webhooks import register_bot_commands
from biotact.core.config import get_settings
from biotact.core.database import close_db
from biotact.modules import module_registry
from biotact.modules.callcenter.config import callcenter_config
from biotact.modules.dashboard.config import dashboard_config
from biotact.modules.hr.config import hr_config
from biotact.modules.marketing.config import marketing_config


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    # Startup - register department modules
    module_registry.register(dashboard_config)
    module_registry.register(callcenter_config)
    module_registry.register(marketing_config)
    module_registry.register(hr_config)

    # Register Telegram bot commands (/start, /new, /products, /contact)
    await register_bot_commands()

    yield

    # Shutdown
    await close_db()


settings = get_settings()

app = FastAPI(
    title="Biotact Platform",
    description="AI-powered RAG system for Biotact pharmaceutical company",
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router)


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {
        "name": "Biotact Platform",
        "version": __version__,
        "docs": "/docs",
    }
