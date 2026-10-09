"""Общая конфигурация pytest для бэкенда ПЭН.

Запуск тестов:
    cd backend
    pytest

Тесты не требуют запущенных PostgreSQL / Redis / Docker:
- вместо PostgreSQL используется файловый SQLite (JSONB подменяется на sqlite JSON);
- Redis заменяется in-memory заглушкой (только отзыв JWT-токенов и кэш пользователя);
- rate limiting (slowapi) и FastAPICache — отключены;
- на Windows, где отсутствует нативная библиотека libmagic, модуль `magic`
  (python-magic) подменяется заглушкой. Если libmagic установлена — используется
  настоящий модуль.
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

# ── Обязательные переменные окружения ДО импорта app.* ────────────────────
_TEST_DB = (Path(__file__).resolve().parent / "test_pen_test.db").as_posix()
os.environ.setdefault("DATABASE_URL", f"sqlite+pysqlite:///{_TEST_DB}")
os.environ.setdefault("SECRET_KEY", "test-secret-key-0123456789-abcdef")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("REDIS_URL", "redis://:testpass@localhost:6379/0")
os.environ.setdefault("RATE_LIMIT_LOGIN", "100000/minute")
os.environ.setdefault("DEBUG", "False")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "TestPass123!")
os.environ.setdefault("ADMIN_EMAIL", "admin@test.ru")
os.environ.setdefault("CORS_ORIGINS", "http://localhost")

# ── SQLite не знает тип JSONB — подменяем его до импорта моделей ──────────
# Приложение использует postgres-специфичный `data['key'].astext` (компилируется
# в `->>`). В SQLite sqlite-JSON индексация даёт `JSON_QUOTE(JSON_EXTRACT(...))`
# с кавычками, что ломает сравнения строк. Эмулируем `.astext` через оператор
# SQLite `->>` (доступен с SQLite 3.38), возвращающий значение без кавычек.
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.sqlite import JSON as _SQLiteJSON


class _PortableJSON(_SQLiteJSON):
    """sqlite JSON, в котором `data['key'].astext` компилируется как `->>`."""

    class comparator_factory(_SQLiteJSON.comparator_factory):
        @property
        def astext(self):
            expr = self.expr
            return expr.left.op("->>")(expr.right)


postgresql.JSONB = _PortableJSON

# ── python-magic: заглушка только если нет нативной libmagic ──────────────
try:
    import magic  # noqa: F401
except Exception:
    _fake_magic = types.ModuleType("magic")

    def _detect(_buf) -> str:
        return "application/octet-stream"

    _fake_magic.from_buffer = _detect
    _fake_magic.from_file = _detect
    _fake_magic.detect_from_content = _detect
    _fake_magic.detect_from_file = _detect
    _fake_magic.MagicError = Exception
    sys.modules.setdefault("magic", _fake_magic)

# ── Отключаем rate limiting и реальный Async-кэш (Redis не поднят) ────────
from app.limiter import limiter  # noqa: E402
import fastapi_cache  # noqa: E402

limiter.enabled = False


async def _noop_cache_clear(*args, **kwargs):
    return None


fastapi_cache.FastAPICache.clear = staticmethod(_noop_cache_clear)

from app import auth as _auth_module  # noqa: E402
from app.database import Base, engine, SessionLocal  # noqa: E402

import pytest  # noqa: E402


class FakeRedis:
    """Минимальная in-memory заглушка Redis для auth (jti, кэш пользователя)."""

    def __init__(self):
        self._store: dict = {}

    def setex(self, key, ttl, value):
        self._store[key] = value

    def set(self, key, value, **kwargs):
        self._store[key] = value

    def get(self, key):
        return self._store.get(key)

    def delete(self, *keys):
        removed = 0
        for key in keys:
            if self._store.pop(key, None) is not None:
                removed += 1
        return removed

    def exists(self, key):
        return int(key in self._store)


@pytest.fixture(scope="session")
def fake_redis():
    fake = FakeRedis()
    _auth_module.get_redis = lambda: fake
    return fake


@pytest.fixture()
def db_session(fake_redis):
    """Свежая схема БД и сессия под каждый тест."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session, fake_redis):
    """TestClient с полным приложением (lifespan создаёт admin и роли)."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


def login(client, username: str, password: str):
    """Логин через API. Возвращает ответ."""
    return client.post("/api/auth/login", json={"username": username, "password": password})


def csrf_headers(client) -> dict:
    """POST/PUT/PATCH/DELETE требуют X-CSRF-Token (double-submit cookie)."""
    return {"X-CSRF-Token": client.cookies.get("csrf_token", "")}