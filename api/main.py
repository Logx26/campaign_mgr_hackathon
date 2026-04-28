"""FastAPI application factory."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import briefs, health, plans, sessions


def create_app() -> FastAPI:
    app = FastAPI(
        title="Campaign Management API",
        version="0.1.0",
        description=(
            "AI-assisted campaign brief-to-plan workflow with clarification dialog, "
            "plan QA (W2), and multi-asset consistency (W3)."
        ),
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8501", "http://ui:8501"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(sessions.router, prefix="/api/v1")
    app.include_router(briefs.router, prefix="/api/v1")
    app.include_router(plans.router, prefix="/api/v1")

    return app


app = create_app()
