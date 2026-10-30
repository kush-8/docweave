"""Public configured metadata; this module never calls a hosted provider."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from docweave.auth import auth_service
from docweave.pagination import decode_cursor, page


class ProcessorView(BaseModel):
    id: str
    provider: Literal["gemini", "groq", "huggingface"]
    backend: str
    roles: list[str]


class ProviderProfileView(BaseModel):
    id: UUID
    provider: Literal["gemini", "groq", "huggingface"]
    model: str
    backend: str
    enabled: bool
    disabled_reason: str | None = Field(None, exclude_if=lambda value: value is None)
    processors: list[ProcessorView]


class ProviderPage(BaseModel):
    items: list[ProviderProfileView]
    next_cursor: str | None


router = APIRouter(prefix="/api/v1", tags=["Catalog"])


@router.get("/providers", operation_id="listProviderProfiles", response_model=ProviderPage,
    responses={400: {"description": "Invalid cursor."}, 503: {"description": "Application services are not configured."}},
    description="Configured immutable answer-profile versions with safe eligibility status. Empty until operator configuration; no live capability or provider call is performed.")
async def list_profiles(request: Request, limit: int = Query(25, ge=1, le=100),
    cursor: str | None = Query(None, min_length=1, max_length=2048)):
    settings, engine, _ = auth_service(request)
    after, after_id = decode_cursor(settings, cursor, "public", "providers:v1")
    async with engine.connect() as connection:
        rows = (await connection.execute(text("""
            SELECT p.id,p.created_at,p.provider,p.model,p.backend,app.profile_disabled_reason(p.id) AS disabled_reason,
                app.profile_disabled_reason(p.id) IS NULL AS enabled,
                coalesce((SELECT jsonb_agg(jsonb_build_object('id',pr.id,'provider',pr.provider,'backend',pr.backend,'roles',pr.roles) ORDER BY pr.id)
                    FROM app.processors pr WHERE p.processor_ids ? pr.id),'[]'::jsonb) AS processors
            FROM app.provider_profiles p WHERE p.role='generation' AND (CAST(:after AS timestamptz) IS NULL OR (p.created_at,p.id)>(:after,:id))
            ORDER BY p.created_at,p.id LIMIT :limit
        """), {"after": after, "id": after_id, "limit": limit + 1})).mappings().all()
    return page(settings, [dict(row) for row in rows], limit, "public", "providers:v1")
