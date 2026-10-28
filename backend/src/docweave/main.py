"""Runnable HTTP skeleton. Feature operations deliberately perform no work."""

import re
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from docweave.routes import FEATURE_ROUTES


class Health(BaseModel):
    status: Literal["ok"]


class ApiError(BaseModel):
    code: str
    message: str
    request_id: str
    retryable: bool


ERRORS = {
    404: ("not_found", "Resource not found.", False),
    405: ("method_not_allowed", "Method not allowed.", False),
    500: ("internal_error", "An internal error occurred.", False),
    501: ("not_implemented", "This operation is not implemented yet.", False),
    503: ("not_ready", "Required application services are not implemented yet.", True),
}


def error_response(request: Request, status: int, headers=None) -> JSONResponse:
    code, message, retryable = ERRORS.get(status, ("http_error", "Request failed.", False))
    request_id = request.state.request_id
    return JSONResponse(
        status_code=status,
        content={"code": code, "message": message, "request_id": request_id, "retryable": retryable},
        headers={**(headers or {}), "X-Request-ID": request_id, "Cache-Control": "no-store"},
    )


async def not_implemented():
    raise HTTPException(status_code=501)


def create_app() -> FastAPI:
    app = FastAPI(
        title="DocWeave API skeleton",
        version="0.1.0",
        description="Only liveness is operational. Readiness is unavailable; all feature operations return 501.",
    )

    @app.middleware("http")
    async def response_headers(request: Request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        return error_response(request, exc.status_code, exc.headers)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        return error_response(request, 500)

    @app.get("/api/v1/health/live", response_model=Health, operation_id="getLiveness", tags=["Health"])
    async def liveness():
        return {"status": "ok"}

    @app.get("/api/v1/health/ready", response_model=ApiError, status_code=503,
             operation_id="getReadiness", tags=["Health"])
    async def readiness():
        raise HTTPException(status_code=503)

    for method, path, operation_id, tag in FEATURE_ROUTES:
        app.add_api_route(
            f"/api/v1{path}",
            not_implemented,
            methods=[method],
            operation_id=operation_id,
            tags=[tag],
            status_code=501,
            response_model=ApiError,
            summary=f"{operation_id} (not implemented)",
            description="Reserved route. No authentication, input processing, or business behavior is implemented.",
            openapi_extra={"parameters": [
                {"name": name, "in": "path", "required": True, "schema": {"type": "string"}}
                for name in re.findall(r"\{([^}]+)\}", path)
            ]},
        )

    return app
