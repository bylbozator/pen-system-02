from datetime import timedelta, datetime

from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, Query, Cookie
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.limiter import limiter
from jose import jwt

from app import auth, schemas, models
from app.database import get_db
from app.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"], redirect_slashes=False)


# ---------- Вспомогательная модель для ответа на логин ----------
class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user: schemas.UserOut


class PasswordChange(BaseModel):
    old_password: str
    new_password: str


@router.post("/login", response_model=LoginResponse)
@limiter.limit("5/minute")
def login(
    request: Request,
    login_data: schemas.LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    user = auth.authenticate_user(db, login_data.username, login_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверное имя пользователя или пароль",
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    is_secure = request.headers.get("x-forwarded-proto", "http") == "https"
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=is_secure,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    # Сериализуем пользователя для фронтенда
    user_out = schemas.UserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        role_id=user.role_id,
        role_name=user.role.name if user.role else None,
        is_active=user.is_active,
        last_login=user.last_login,
        created_at=user.created_at,
        last_name=user.last_name,
        first_name=user.first_name,
        middle_name=user.middle_name,
        department=getattr(user, "department", None),
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user_out,
    }


@router.post("/logout")
def logout(response: Response, access_token: str = Cookie(None)):
    if access_token:
        try:
            payload = jwt.decode(access_token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            jti = payload.get("jti")
            exp = payload.get("exp", 0)
            if jti:
                ttl = max(exp - int(datetime.utcnow().timestamp()), 60)
                auth.revoke_token(jti, ttl)
        except Exception:
            pass
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


@router.get("/me", response_model=schemas.UserOut)
def read_users_me(current_user: models.User = Depends(auth.get_current_active_user)):
    return schemas.UserOut(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        role_id=current_user.role_id,
        role_name=current_user.role.name if current_user.role else None,
        is_active=current_user.is_active,
        last_login=current_user.last_login,
        created_at=current_user.created_at,
        last_name=current_user.last_name,
        first_name=current_user.first_name,
        middle_name=current_user.middle_name,
        department=current_user.department,
    )


@router.post("/change-password")
@limiter.limit("5/minute")
def change_password(
    request: Request,
    data: PasswordChange,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    if not auth.verify_password(data.old_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Неверный старый пароль")
    auth.validate_password_strength(data.new_password)
    current_user.hashed_password = auth.get_password_hash(data.new_password)
    db.commit()
    auth.invalidate_user_cache(current_user.id)
    return {"ok": True}


@router.get("/me/activity", response_model=schemas.AuditLogResponse)
def my_activity(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    action: str = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    query = db.query(models.UserActionLog).filter(
        models.UserActionLog.user_id == current_user.id
    )
    if action:
        action_pattern = f"%{action}%"
        query = query.filter(models.UserActionLog.action.ilike(action_pattern))
    total = query.count()
    logs = query.order_by(models.UserActionLog.created_at.desc()).offset(skip).limit(limit).all()
    items = []
    for log in logs:
        items.append(schemas.AuditLogEntry(
            id=log.id,
            user_id=log.user_id,
            username=current_user.username,
            action=log.action,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            details=log.details,
            ip_address=log.ip_address,
            user_agent=log.user_agent,
            created_at=log.created_at,
        ))
    return schemas.AuditLogResponse(items=items, total=total, skip=skip, limit=limit)