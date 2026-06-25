# backend/app/middleware/csrf.py

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from itsdangerous import URLSafeTimedSerializer
from app.config import settings

serializer = URLSafeTimedSerializer(settings.SECRET_KEY)

def generate_csrf_token():
    return serializer.dumps("csrf")

def verify_csrf_token(token: str):
    try:
        serializer.loads(token, max_age=3600)
        return True
    except:
        return False

CSRF_TOKEN_EXEMPT_PATHS = {
    "/api/auth/login",
    "/api/auth/logout",
    "/api/import-export/import",
    "/api/import-export/preview",
    "/auth/login",
    "/auth/logout",
}

def _set_csrf_cookie(response, token=None):
    response.set_cookie(
        key="csrf_token",
        value=token or generate_csrf_token(),
        httponly=False,
        samesite="lax",
        secure=not settings.DEBUG,
        path="/",
    )

class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in {"POST", "PUT", "DELETE", "PATCH"}:
            path = request.url.path
            if path not in CSRF_TOKEN_EXEMPT_PATHS:
                token = request.headers.get("X-CSRF-Token")
                if not token or not verify_csrf_token(token):
                    resp = JSONResponse(
                        status_code=403,
                        content={"detail": "CSRF-токен отсутствует или недействителен"},
                    )
                    _set_csrf_cookie(resp)
                    return resp
        response = await call_next(request)
        if not request.cookies.get("csrf_token"):
            _set_csrf_cookie(response)
        return response
