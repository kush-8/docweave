from fastapi import APIRouter, Query, Request
from docweave.api.dependencies.auth import auth_service
from docweave.core.pagination import decode_cursor, page
from docweave.repositories import providers as repository
from docweave.schemas.providers import ProviderPage


router = APIRouter(prefix="/api/v1", tags=["Catalog"])


@router.get("/providers", operation_id="listProviderProfiles", response_model=ProviderPage,
    responses={400: {"description": "Invalid cursor."}, 503: {"description": "Application services are not configured."}},
    description="Configured immutable answer-profile versions with safe eligibility status. Empty until operator configuration; no live capability or provider call is performed.")
async def list_profiles(request: Request, limit: int = Query(25, ge=1, le=100),
    cursor: str | None = Query(None, min_length=1, max_length=2048)):
    settings, engine, _ = auth_service(request)
    after, after_id = decode_cursor(settings, cursor, "public", "providers:v1")
    async with engine.connect() as connection:
        rows = (await repository.list_profiles(connection, {"after": after, "id": after_id, "limit": limit + 1})).mappings().all()
    return page(settings, [dict(row) for row in rows], limit, "public", "providers:v1")
