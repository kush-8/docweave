from fastapi.security import APIKeyCookie, APIKeyHeader


session_cookie = APIKeyCookie(name="docweave_session", scheme_name="sessionCookie", auto_error=False)
csrf_header = APIKeyHeader(name="X-CSRF-Token", scheme_name="csrfToken", auto_error=False)

def cookie_value(request, name):
    value = request.cookies.get(name, "")
    return value if len(value) == 64 and all(c in "0123456789abcdef" for c in value) else ""


def set_cookie(response, name, value, settings, max_age):
    response.set_cookie(name, value, max_age=max_age, httponly=True, secure=settings.secure, samesite="lax", path="/")
