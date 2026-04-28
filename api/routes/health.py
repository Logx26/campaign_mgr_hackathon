"""Liveness + dependency-readiness probe."""
from __future__ import annotations

from typing import Literal

import httpx
import redis
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from core.config import get_settings
from core.db.session import get_engine

router = APIRouter()


class DependencyStatus(BaseModel):
    name: str
    ok: bool
    detail: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str = "campaign-mgr-api"
    version: str = "0.1.0"
    dependencies: list[DependencyStatus]


def _check_postgres() -> DependencyStatus:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return DependencyStatus(name="postgres", ok=True)
    except Exception as exc:
        return DependencyStatus(name="postgres", ok=False, detail=str(exc))


def _check_redis() -> DependencyStatus:
    try:
        client = redis.Redis.from_url(get_settings().REDIS_URL, socket_connect_timeout=2)
        client.ping()
        return DependencyStatus(name="redis", ok=True)
    except Exception as exc:
        return DependencyStatus(name="redis", ok=False, detail=str(exc))


def _check_qdrant() -> DependencyStatus:
    try:
        url = f"{get_settings().QDRANT_URL.rstrip('/')}/collections"
        with httpx.Client(timeout=2.0) as client:
            r = client.get(url)
            r.raise_for_status()
        return DependencyStatus(name="qdrant", ok=True)
    except Exception as exc:
        return DependencyStatus(name="qdrant", ok=False, detail=str(exc))


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    deps = [_check_postgres(), _check_redis(), _check_qdrant()]
    overall = "ok" if all(d.ok for d in deps) else "degraded"
    return HealthResponse(status=overall, dependencies=deps)
