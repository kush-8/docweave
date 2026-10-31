from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from docweave.core.errors import DomainError


ERRORS = {
    400: ("invalid_auth", "Sign-in failed. Please start sign-in again.", False),
    401: ("unauthenticated", "Sign in to continue.", False),
    403: ("csrf_failed", "The request origin or security token is invalid.", False),
    404: ("not_found", "Resource not found.", False),
    405: ("method_not_allowed", "Method not allowed.", False),
    413: ("upload_too_large", "The upload exceeds the allowed size.", False),
    422: ("invalid_request", "The request is invalid.", False),
    429: ("rate_limited", "Too many sign-in attempts. Try again shortly.", True),
    500: ("internal_error", "An internal error occurred.", False),
    501: ("not_implemented", "This operation is not implemented yet.", False),
    503: ("not_ready", "Required application services are unavailable.", True),
}


EXPECTED_ERRORS = {
    (400, "invalid_cursor"): ("invalid_cursor", "The pagination cursor is invalid.", False),
    (403, "forbidden"): ("forbidden", "You do not have permission for this operation.", False),
    (409, "last_owner"): ("last_owner", "The last workspace owner cannot be removed or demoted.", False),
    (409, "already_member"): ("already_member", "You already belong to this workspace.", False),
    (409, "revision_conflict"): ("revision_conflict", "The resource changed. Reload it before editing.", False),
    (409, "ingestion_active"): ("ingestion_active", "Another ingestion is active for this document.", True),
}


def error_response(request: Request, status: int, headers=None, detail=None) -> JSONResponse:
    code, message, retryable = EXPECTED_ERRORS.get((status, detail), ERRORS.get(status, ("http_error", "Request failed.", False)))
    request_id = request.state.request_id
    return JSONResponse(
        status_code=status,
        content={"code": code, "message": message, "request_id": request_id, "retryable": retryable},
        headers={**(headers or {}), "X-Request-ID": request_id, "Cache-Control": "no-store"},
    )


DOMAIN_HTTP = {"invalid_auth": (400, None), "invalid_cursor": (400, "invalid_cursor"),
    "unauthenticated": (401, None), "forbidden": (403, "forbidden"), "not_found": (404, None),
    "last_owner": (409, "last_owner"), "already_member": (409, "already_member"),
    "revision_conflict": (409, "revision_conflict"), "ingestion_active": (409, "ingestion_active"),
    "invalid_request": (422, None), "rate_limited": (429, None), "not_implemented": (501, None), "not_ready": (503, None)}

def install_error_handlers(app):
    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        return error_response(request, 422)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        return error_response(request, exc.status_code, exc.headers, exc.detail if isinstance(exc.detail, str) else None)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        return error_response(request, 500)

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError):
        status, detail = DOMAIN_HTTP.get(exc.code, (500, None))
        return error_response(request, status, exc.headers, detail)
