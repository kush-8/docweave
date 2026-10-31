from fastapi import HTTPException, APIRouter
from docweave.api.routes.auth import router
from docweave.schemas.health import Health, ApiError


router = APIRouter()

@router.get("/api/v1/health/live", response_model=Health, operation_id="getLiveness", tags=["Health"])
async def liveness():
    return {"status": "ok"}

@router.get("/api/v1/health/ready", response_model=ApiError, status_code=503,
         operation_id="getReadiness", tags=["Health"])
async def readiness():
    raise HTTPException(status_code=503)
