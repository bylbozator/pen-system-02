import asyncio
from datetime import datetime, timedelta
import json
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from fastapi import HTTPException, status, Depends, Cookie, Header
from app import models
from app.config import settings
from app.database import get_db
from app.redis_client import get_redis
import re
import secrets

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def authenticate_user(db: Session, username: str, password: str):
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        return False
    return user

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    now = datetime.utcnow()
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({
        "exp": expire,
        "iat": now,
        "jti": secrets.token_urlsafe(16),
    })
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def revoke_token(jti: str, expires_in: int = 3600):
    r = get_redis()
    r.setex(f"revoked:{jti}", expires_in, "1")


def is_token_revoked(jti: str) -> bool:
    r = get_redis()
    return r.exists(f"revoked:{jti}") == 1

def validate_password_strength(password: str) -> bool:
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Пароль должен содержать минимум 8 символов")
    if not re.search(r"\d", password):
        raise HTTPException(status_code=400, detail="Пароль должен содержать хотя бы одну цифру")
    if not re.search(r"[A-Z]", password):
        raise HTTPException(status_code=400, detail="Пароль должен содержать хотя бы одну заглавную букву")
    if not re.search(r"[a-z]", password):
        raise HTTPException(status_code=400, detail="Пароль должен содержать хотя бы одну строчную букву")
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        raise HTTPException(status_code=400, detail="Пароль должен содержать хотя бы один специальный символ")
    return True

def get_cached_user(user_id: int, db: Session):
    cache_key = f"user:{user_id}"
    r = get_redis()
    cached = r.get(cache_key)
    if cached:
        user_data = json.loads(cached)
        return user_data
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user:
        user_dict = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role_id": user.role_id,
            "is_active": user.is_active,
            "department": user.department if hasattr(user, 'department') else None,
            "role_name": user.role.name if user.role else None,
            "permissions": user.role.permissions if user.role else {},
        }
        r.setex(cache_key, 300, json.dumps(user_dict))
        return user_dict
    return None

def invalidate_user_cache(user_id: int):
    get_redis().delete(f"user:{user_id}")

async def get_current_user_from_cookie(
    access_token: str = Cookie(None),
    authorization: str = Header(None),
    db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не удалось проверить учетные данные",
    )
    token = access_token
    if not token and authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
    if not token:
        raise credentials_exception
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id: int = int(payload.get("sub"))
        jti: str = payload.get("jti")
        if user_id is None or jti is None:
            raise credentials_exception
        if await asyncio.to_thread(is_token_revoked, jti):
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise credentials_exception
    return user

async def get_current_active_user(current_user: models.User = Depends(get_current_user_from_cookie)):
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Пользователь деактивирован")
    return current_user

def has_permission(user: models.User, permission: str, db: Session) -> bool:
    role = user.role
    if not role:
        return False
    perms = role.permissions or {}
    return perms.get(permission, False) or perms.get("full_access", False)
