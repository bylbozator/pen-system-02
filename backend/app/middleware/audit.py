from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
import time
from app.services.audit_service import log_action
from app.database import SessionLocal
from jose import jwt
from app.config import settings
import structlog

logger = structlog.get_logger()

class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        try:
            response = await call_next(request)
        except Exception as e:
            process_time = time.time() - start_time
            user_id = None
            token = None
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
            else:
                token = request.cookies.get("access_token")
            if token:
                try:
                    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
                    user_id = payload.get("sub")
                except Exception as e:
                    logger.debug("Could not decode JWT in error handler", error=str(e))
            ip = request.client.host if request.client else ""
            user_agent = request.headers.get("user-agent", "")
            logger.error(
                "Request processing failed",
                method=request.method,
                path=request.url.path,
                duration=process_time,
                error=str(e),
                user_id=user_id,
                ip=ip,
                user_agent=user_agent,
                exc_info=True
            )
            db = SessionLocal()
            try:
                log_action(db, user_id, f"{request.method} {request.url.path}", "ERROR", "", {"error": str(e), "duration": process_time}, ip, user_agent)
                db.commit()
            finally:
                db.close()
            raise

        process_time = time.time() - start_time
        if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
            user_id = None
            token = None
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
            else:
                token = request.cookies.get("access_token")
            if token:
                try:
                    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
                    user_id = payload.get("sub")
                except Exception as e:
                    logger.debug("Could not decode JWT for audit log", error=str(e))
            ip = request.client.host if request.client else ""
            user_agent = request.headers.get("user-agent", "")
            logger.info(
                "Request processed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration=process_time,
                user_id=user_id,
                ip=ip,
                user_agent=user_agent
            )
            db = SessionLocal()
            try:
                log_action(db, user_id, f"{request.method} {request.url.path}", request.method, "", {"status": response.status_code, "duration": process_time}, ip, user_agent)
                db.commit()
            finally:
                db.close()
        return response
