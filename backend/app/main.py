# backend/app/main.py
# ПЭН Система — система учёта и контроля поставок материально-технических ресурсов (МТР)
# для производственно-эксплуатационных нужд. Обеспечивает работу с электронными таблицами
# (план/факт), разграничение доступа, аудит действий, импорт/экспорт Excel и PDF-парсер.

import asyncio
from contextlib import asynccontextmanager
from collections import defaultdict
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.limiter import limiter
from prometheus_fastapi_instrumentator import Instrumentator

from app.celery_app import celery_app
from app.routers import datasets, rows, import_export, admin, auth, comments, pdf_parser
from app.middleware.audit import AuditMiddleware
from app.middleware.csrf import CSRFMiddleware
from app.database import engine, Base, get_db
from app.config import settings
from app import models, auth as auth_module
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
import redis.asyncio as aioredis
import os
import structlog
from app.logging_config import setup_logging
from app.websocket_manager import manager
from jose import jwt
import json

logger = structlog.get_logger()



@asynccontextmanager
async def lifespan(app: FastAPI):
    # ----- STARTUP -----
    setup_logging()
    logger.info("Application starting", debug=settings.DEBUG)

    # Инициализация кэша FastAPI
    redis = aioredis.from_url(settings.REDIS_URL)
    FastAPICache.init(RedisBackend(redis), prefix="pen-cache")

    # Создание таблиц, если их ещё нет (резерв для случаев без миграций)
    Base.metadata.create_all(bind=engine)

    # Создание администратора при первом запуске
    try:
        db_session = next(get_db())
        admin_role = db_session.query(models.UserRole).filter(
            models.UserRole.name == "администратор"
        ).first()
        if not admin_role:
            admin_role = models.UserRole(
                name="администратор",
                permissions={
                    "full_access": True,
                    "can_view_all_datasets": True,
                    "can_edit_all_datasets": True,
                    "can_create_datasets": True,
                    "can_manage_users": True,
                    "can_manage_roles": True,
                    "can_manage_schemas": True,
                    "can_view_reports": True,
                    "can_export": True,
                    "can_import": True,
                },
                description="Полный доступ ко всем функциям системы",
            )
            db_session.add(admin_role)
            db_session.commit()

        admin_user = db_session.query(models.User).filter(
            models.User.username == settings.ADMIN_USERNAME
        ).first()
        if not admin_user:
            from app.auth import get_password_hash
            admin_user = models.User(
                username=settings.ADMIN_USERNAME,
                email=settings.ADMIN_EMAIL,
                hashed_password=get_password_hash(settings.ADMIN_PASSWORD),
                role_id=admin_role.id,
                is_active=True,
            )
            db_session.add(admin_user)
            logger.info("Default admin user created", username=settings.ADMIN_USERNAME)
        elif admin_user.role_id != admin_role.id:
            admin_user.role_id = admin_role.id
            logger.info("Admin user role_id corrected to match administrator role")

        # Дополнительные роли (создаются, если их нет)
        additional_roles = [
            {
                "name": "снабжение",
                "permissions": {"can_create_datasets": True, "can_edit_own_sheets": True, "can_import": True},
                "description": "Отдел снабжения",
            },
            {
                "name": "экономист",
                "permissions": {"can_edit_rows": True, "can_edit_fact_data": True, "can_view_reports": True},
                "description": "Планово-экономический отдел",
            },
            {
                "name": "руководитель",
                "permissions": {"can_view_all_datasets": True, "can_edit_all_datasets": True, "can_view_reports": True},
                "description": "Руководство",
            },
        ]
        for role_data in additional_roles:
            exists = db_session.query(models.UserRole).filter(
                models.UserRole.name == role_data["name"]
            ).first()
            if not exists:
                db_session.add(models.UserRole(
                    name=role_data["name"],
                    permissions=role_data["permissions"],
                    description=role_data["description"],
                ))
        db_session.commit()
    except Exception as e:
        logger.error("Failed to create admin user", error=str(e))
    finally:
        if db_session:
            db_session.close()

    # Логирование зарегистрированных маршрутов при DEBUG=True
    if settings.DEBUG:
        routes_info = []
        for route in app.routes:
            if hasattr(route, 'methods'):
                routes_info.append({
                    "methods": list(route.methods),
                    "path": route.path,
                })
            else:
                routes_info.append({"methods": ["WS"], "path": route.path})
        logger.debug("Registered routes", routes=routes_info)

    # ----- ПРИЛОЖЕНИЕ РАБОТАЕТ -----
    yield

    # ----- SHUTDOWN -----
    await redis.close()
    await FastAPICache.clear()
    logger.info("Application shutting down")


# Создаём приложение с lifespan
app = FastAPI(
    title="PEN System API",
    debug=settings.DEBUG,
    lifespan=lifespan,
)


# Настройка CORS – разрешаем запросы с фронтенда (в т.ч. с куками)
origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost,https://localhost").split(",")
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Ограничитель запросов (использует Redis)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Middleware аудита (логирование действий)
app.add_middleware(AuditMiddleware)


# Включаем CSRF-защиту
app.add_middleware(CSRFMiddleware)


# Подключаем роутеры
app.include_router(auth.router)
app.include_router(datasets.router)
app.include_router(rows.router)
app.include_router(import_export.router)
app.include_router(admin.router)
app.include_router(comments.router)
app.include_router(pdf_parser.router)


# Инструментация для Prometheus (метрики доступны по /metrics)
Instrumentator().instrument(app).expose(app, include_in_schema=True)


@app.get("/")
def root():
    return {"message": "PEN System API"}


@app.get("/health")
def health_check():
    from sqlalchemy import text
    from app.database import SessionLocal
    from app.redis_client import get_redis

    db_ok = False
    redis_ok = False

    db = None
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        logger.warning("Health check: database check failed", error=str(e))
    finally:
        if db is not None:
            db.close()

    try:
        r = get_redis()
        r.ping()
        redis_ok = True
    except Exception as e:
        logger.warning("Health check: redis check failed", error=str(e))

    return {
        "status": "healthy" if db_ok and redis_ok else "unhealthy",
        "database": db_ok,
        "redis": redis_ok,
    }


WS_MAX_MSG_SIZE = 1024 * 100  # 100KB
WS_RATE_LIMIT = 60  # сообщений в минуту

ws_rate_counters: dict[str, list[float]] = defaultdict(list)


@app.websocket("/ws/{dataset_id}")
async def websocket_endpoint(websocket: WebSocket, dataset_id: int, token: str = ""):
    user_id = None
    # Пробуем взять токен из query-параметра, затем из cookie
    raw_token = token or websocket.cookies.get("access_token") or ""
    if raw_token:
        try:
            payload = jwt.decode(raw_token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            user_id_str = payload.get("sub")
            jti = payload.get("jti")
            if user_id_str is not None:
                if jti is not None and await asyncio.to_thread(auth_module.is_token_revoked, jti):
                    await websocket.close(code=4001, reason="Token revoked")
                    return
                user_id = int(user_id_str)
        except Exception:
            pass
    if not user_id:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    # Проверяем права доступа к датасету
    try:
        db = next(get_db())
        dataset = db.query(models.Dataset).filter(models.Dataset.id == dataset_id).first()
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not dataset:
            await websocket.close(code=4004, reason="Dataset not found")
            return
        if not user or not user.is_active:
            await websocket.close(code=4001, reason="Unauthorized")
            return
        has_access = (
            auth_module.has_permission(user, "full_access", db) or
            auth_module.has_permission(user, "can_view_all_datasets", db) or
            dataset.owner_id == user.id or
            auth_module.has_permission(user, "can_view_datasets", db)
        )
        if not has_access:
            await websocket.close(code=4003, reason="Access denied")
            return
    finally:
        db.close()

    user_key = f"ws:{user_id}"
    await manager.connect(websocket, dataset_id)
    try:
        while True:
            data = await websocket.receive_text()
            # Rate limiting
            now = time.time()
            ws_rate_counters[user_key] = [t for t in ws_rate_counters[user_key] if now - t < 60]
            if len(ws_rate_counters[user_key]) >= WS_RATE_LIMIT:
                await websocket.send_json({"type": "error", "message": "Rate limit exceeded"})
                continue
            ws_rate_counters[user_key].append(now)
            # Size validation
            if len(data) > WS_MAX_MSG_SIZE:
                await websocket.send_json({"type": "error", "message": "Message too large"})
                continue
            try:
                msg = json.loads(data)
                msg_type = msg.get("type", "")
                if msg_type in ("cell_updated", "cursor_moved", "user_joined"):
                    msg["user_id"] = user_id
                    await manager.broadcast(dataset_id, msg)
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket, dataset_id)
        ws_rate_counters.pop(user_key, None)