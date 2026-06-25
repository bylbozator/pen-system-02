from fastapi import APIRouter, Depends, HTTPException, Query, Body, Response
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from app import models, schemas, auth
from app.database import get_db
from app.services.audit_service import log_action
from app.utils import dataset_to_out, user_to_out
from passlib.context import CryptContext
import structlog

router = APIRouter(prefix="/api/admin", tags=["admin"], redirect_slashes=False)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
logger = structlog.get_logger()


class ResetPasswordRequest(BaseModel):
    new_password: str

# ======================== ЗАВИСИМОСТИ ========================
def require_admin(
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db)
) -> models.User:
    """Проверяет, что пользователь имеет права администратора (full_access)."""
    if not auth.has_permission(current_user, "full_access", db):
        raise HTTPException(status_code=403, detail="Требуются права администратора")
    return current_user

# ======================== ПОЛЬЗОВАТЕЛИ ========================
@router.get("/users", response_model=List[schemas.UserOut])
def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    role_id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin)
):
    query = db.query(models.User)
    if role_id is not None:
        query = query.filter(models.User.role_id == role_id)
    if is_active is not None:
        query = query.filter(models.User.is_active == is_active)
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            (models.User.username.ilike(search_pattern)) |
            (models.User.email.ilike(search_pattern)) |
            (models.User.last_name.ilike(search_pattern)) |
            (models.User.first_name.ilike(search_pattern))
        )
    users = query.order_by(models.User.id).offset(skip).limit(limit).all()
    return [user_to_out(u) for u in users]

@router.get("/users/{user_id}", response_model=schemas.UserOut)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin)
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user_to_out(user)

@router.post("/users", response_model=schemas.UserOut, status_code=201)
def create_user(
    user: schemas.UserCreate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin)
):
    if db.query(models.User).filter(models.User.username == user.username).first():
        raise HTTPException(status_code=400, detail="Имя пользователя уже существует")
    if db.query(models.User).filter(models.User.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email уже существует")
    role = db.query(models.UserRole).filter(models.UserRole.id == user.role_id).first()
    if not role:
        raise HTTPException(status_code=400, detail="Указанная роль не существует")

    hashed = pwd_context.hash(user.password)
    db_user = models.User(
        username=user.username,
        email=user.email,
        hashed_password=hashed,
        last_name=user.last_name,
        first_name=user.first_name,
        middle_name=user.middle_name,
        department=user.department,
        role_id=user.role_id,
        is_active=True,
        created_by=current_admin.id
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    auth.invalidate_user_cache(db_user.id)
    log_action(db, current_admin.id, "CREATE_USER", "USER", str(db_user.id),
               {"username": user.username, "email": user.email, "role_id": user.role_id})
    return user_to_out(db_user)

@router.post("/users/batch", response_model=dict, status_code=201)
def batch_create_users(
    users: List[schemas.UserCreate],
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin)
):
    created = 0
    errors = []
    for idx, user_data in enumerate(users):
        try:
            if db.query(models.User).filter(models.User.username == user_data.username).first():
                errors.append(f"Строка {idx + 1}: Имя пользователя '{user_data.username}' уже существует")
                continue
            if db.query(models.User).filter(models.User.email == user_data.email).first():
                errors.append(f"Строка {idx + 1}: Email '{user_data.email}' уже существует")
                continue
            role = db.query(models.UserRole).filter(models.UserRole.id == user_data.role_id).first()
            if not role:
                errors.append(f"Строка {idx + 1}: Роль с ID {user_data.role_id} не существует")
                continue
            try:
                auth.validate_password_strength(user_data.password)
            except HTTPException as e:
                errors.append(f"Строка {idx + 1}: {e.detail}")
                continue
            hashed = pwd_context.hash(user_data.password)
            db_user = models.User(
                username=user_data.username,
                email=user_data.email,
                hashed_password=hashed,
                last_name=user_data.last_name,
                first_name=user_data.first_name,
                middle_name=user_data.middle_name,
                department=user_data.department,
                role_id=user_data.role_id,
                is_active=True,
                created_by=current_admin.id
            )
            db.add(db_user)
            created += 1
        except Exception as e:
            errors.append(f"Строка {idx + 1}: Неизвестная ошибка - {str(e)}")
    db.commit()
    log_action(db, current_admin.id, "BATCH_CREATE_USERS", "USER", None,
               {"created": created, "errors_count": len(errors)})
    return {"created": created, "errors": errors, "total_processed": len(users)}

@router.patch("/users/{user_id}", response_model=schemas.UserOut)
def update_user(
    user_id: int,
    user_update: schemas.UserUpdate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin)
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if user_id == current_admin.id:
        if user_update.role_id is not None and user_update.role_id != user.role_id:
            raise HTTPException(status_code=403, detail="Нельзя изменить свою роль")
        if user_update.is_active is False:
            raise HTTPException(status_code=403, detail="Нельзя заблокировать самого себя")

    changes = {}
    if user_update.username is not None:
        existing = db.query(models.User).filter(
            models.User.username == user_update.username,
            models.User.id != user_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Имя пользователя уже занято")
        user.username = user_update.username
        changes["username"] = user_update.username
    if user_update.email is not None:
        existing = db.query(models.User).filter(
            models.User.email == user_update.email,
            models.User.id != user_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email уже занят")
        user.email = user_update.email
        changes["email"] = user_update.email
    if user_update.password is not None:
        auth.validate_password_strength(user_update.password)
        user.hashed_password = pwd_context.hash(user_update.password)
        changes["password"] = "changed"
    if user_update.last_name is not None:
        user.last_name = user_update.last_name
        changes["last_name"] = user_update.last_name
    if user_update.first_name is not None:
        user.first_name = user_update.first_name
        changes["first_name"] = user_update.first_name
    if user_update.middle_name is not None:
        user.middle_name = user_update.middle_name
        changes["middle_name"] = user_update.middle_name
    if user_update.department is not None:
        user.department = user_update.department
        changes["department"] = user_update.department
    if user_update.role_id is not None:
        role = db.query(models.UserRole).filter(models.UserRole.id == user_update.role_id).first()
        if not role:
            raise HTTPException(status_code=400, detail="Указанная роль не существует")
        user.role_id = user_update.role_id
        changes["role_id"] = user_update.role_id
    if user_update.is_active is not None:
        user.is_active = user_update.is_active
        changes["is_active"] = user_update.is_active

    db.commit()
    db.refresh(user)
    auth.invalidate_user_cache(user.id)
    log_action(db, current_admin.id, "UPDATE_USER", "USER", str(user.id), changes)
    return user_to_out(user)

@router.delete("/users/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin)
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if user.id == current_admin.id:
        raise HTTPException(status_code=400, detail="Нельзя удалить самого себя")
    username = user.username
    db.delete(user)
    db.commit()
    auth.invalidate_user_cache(user_id)
    log_action(db, current_admin.id, "DELETE_USER", "USER", str(user_id), {"username": username})
    return Response(status_code=204)

@router.post("/users/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    body: ResetPasswordRequest,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin)
):
    new_password = body.new_password
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Пароль должен содержать минимум 8 символов")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    auth.validate_password_strength(new_password)
    user.hashed_password = pwd_context.hash(new_password)
    db.commit()
    auth.invalidate_user_cache(user_id)
    log_action(db, current_admin.id, "RESET_PASSWORD", "USER", str(user.id), {"username": user.username})
    return {"ok": True, "message": f"Пароль пользователя '{user.username}' сброшен"}

# ======================== РОЛИ ========================
@router.get("/roles", response_model=List[schemas.RoleOut])
def list_roles(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin)
):
    return db.query(models.UserRole).order_by(models.UserRole.id).all()

@router.get("/roles/{role_id}", response_model=schemas.RoleOut)
def get_role(
    role_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin)
):
    role = db.query(models.UserRole).filter(models.UserRole.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Роль не найдена")
    return role

@router.post("/roles", response_model=schemas.RoleOut, status_code=201)
def create_role(
    role: schemas.RoleCreate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin)
):
    if db.query(models.UserRole).filter(models.UserRole.name == role.name).first():
        raise HTTPException(status_code=400, detail="Роль с таким названием уже существует")
    db_role = models.UserRole(
        name=role.name,
        permissions=role.permissions,
        description=role.description
    )
    db.add(db_role)
    db.commit()
    db.refresh(db_role)
    log_action(db, current_admin.id, "CREATE_ROLE", "ROLE", str(db_role.id),
               {"name": role.name, "permissions": role.permissions})
    return db_role

@router.patch("/roles/{role_id}", response_model=schemas.RoleOut)
def update_role(
    role_id: int,
    role_update: schemas.RoleUpdate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin)
):
    role = db.query(models.UserRole).filter(models.UserRole.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Роль не найдена")
    changes = {}
    if role_update.name is not None:
        existing = db.query(models.UserRole).filter(
            models.UserRole.name == role_update.name,
            models.UserRole.id != role_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Роль с таким названием уже существует")
        role.name = role_update.name
        changes["name"] = role_update.name
    if role_update.permissions is not None:
        role.permissions = role_update.permissions
        changes["permissions"] = role_update.permissions
    if role_update.description is not None:
        role.description = role_update.description
        changes["description"] = role_update.description
    db.commit()
    db.refresh(role)
    log_action(db, current_admin.id, "UPDATE_ROLE", "ROLE", str(role.id), changes)
    return role

@router.delete("/roles/{role_id}", status_code=204)
def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin)
):
    role = db.query(models.UserRole).filter(models.UserRole.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Роль не найдена")
    users_count = db.query(models.User).filter(models.User.role_id == role_id).count()
    if users_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Роль назначена {users_count} пользователям. Сначала переназначьте им другую роль."
        )
    role_name = role.name
    db.delete(role)
    db.commit()
    log_action(db, current_admin.id, "DELETE_ROLE", "ROLE", str(role_id), {"name": role_name})
    return Response(status_code=204)

@router.post("/roles/{role_id}/duplicate", response_model=schemas.RoleOut, status_code=201)
def duplicate_role(
    role_id: int,
    new_name: str = Query(..., description="Название новой роли"),
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin)
):
    source_role = db.query(models.UserRole).filter(models.UserRole.id == role_id).first()
    if not source_role:
        raise HTTPException(status_code=404, detail="Исходная роль не найдена")
    if db.query(models.UserRole).filter(models.UserRole.name == new_name).first():
        raise HTTPException(status_code=400, detail="Роль с таким названием уже существует")
    new_role = models.UserRole(
        name=new_name,
        permissions=source_role.permissions.copy() if source_role.permissions else {},
        description=f"Копия роли '{source_role.name}'"
    )
    db.add(new_role)
    db.commit()
    db.refresh(new_role)
    log_action(db, current_admin.id, "DUPLICATE_ROLE", "ROLE", str(new_role.id),
               {"source_role_id": role_id, "new_name": new_name})
    return new_role

# ======================== СХЕМЫ ДАТАСЕТОВ ========================
@router.get("/schemas", response_model=List[schemas.DatasetSchemaOut])
def list_schemas(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin)
):
    """Список всех схем датасетов."""
    return db.query(models.DatasetSchema).order_by(models.DatasetSchema.created_at.desc()).all()

@router.get("/schemas/{schema_id}", response_model=schemas.DatasetSchemaOut)
def get_schema(
    schema_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin)
):
    schema = db.query(models.DatasetSchema).filter(models.DatasetSchema.id == schema_id).first()
    if not schema:
        raise HTTPException(status_code=404, detail="Схема не найдена")
    return schema

@router.post("/schemas", response_model=schemas.DatasetSchemaOut, status_code=201)
def create_schema(
    schema: schemas.DatasetSchemaCreate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin)
):
    """Создание новой схемы датасета."""
    if db.query(models.DatasetSchema).filter(models.DatasetSchema.name == schema.name).first():
        raise HTTPException(status_code=400, detail="Схема с таким названием уже существует")
    # Преобразуем ColumnDef в словари
    columns = [col.model_dump() if hasattr(col, 'model_dump') else col for col in schema.columns]
    db_schema = models.DatasetSchema(
        name=schema.name,
        columns=columns,
        header_row_1=schema.header_row_1,
        header_row_2=schema.header_row_2,
        header_row_2_colors=schema.header_row_2_colors,
        created_by=current_admin.id
    )
    db.add(db_schema)
    db.commit()
    db.refresh(db_schema)
    log_action(db, current_admin.id, "CREATE_SCHEMA", "DATASET_SCHEMA", str(db_schema.id),
               {"name": schema.name})
    return db_schema

@router.patch("/schemas/{schema_id}", response_model=schemas.DatasetSchemaOut)
def update_schema(
    schema_id: int,
    schema_update: schemas.DatasetSchemaUpdate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin)
):
    schema = db.query(models.DatasetSchema).filter(models.DatasetSchema.id == schema_id).first()
    if not schema:
        raise HTTPException(status_code=404, detail="Схема не найдена")
    changes = {}
    if schema_update.name is not None:
        existing = db.query(models.DatasetSchema).filter(
            models.DatasetSchema.name == schema_update.name,
            models.DatasetSchema.id != schema_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Схема с таким названием уже существует")
        schema.name = schema_update.name
        changes["name"] = schema_update.name
    if schema_update.columns is not None:
        schema.columns = [col.model_dump() if hasattr(col, 'model_dump') else col for col in schema_update.columns]
        changes["columns"] = "updated"
    if schema_update.header_row_1 is not None:
        schema.header_row_1 = schema_update.header_row_1
        changes["header_row_1"] = "updated"
    if schema_update.header_row_2 is not None:
        schema.header_row_2 = schema_update.header_row_2
        changes["header_row_2"] = "updated"
    if schema_update.header_row_2_colors is not None:
        schema.header_row_2_colors = schema_update.header_row_2_colors
        changes["header_row_2_colors"] = "updated"

    db.commit()
    db.refresh(schema)
    log_action(db, current_admin.id, "UPDATE_SCHEMA", "DATASET_SCHEMA", str(schema.id), changes)
    return schema

@router.delete("/schemas/{schema_id}", status_code=204)
def delete_schema(
    schema_id: int,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin)
):
    schema = db.query(models.DatasetSchema).filter(models.DatasetSchema.id == schema_id).first()
    if not schema:
        raise HTTPException(status_code=404, detail="Схема не найдена")
    # Проверяем, используется ли схема в датасетах
    datasets_count = db.query(models.Dataset).filter(models.Dataset.schema_id == schema_id).count()
    if datasets_count > 0:
        raise HTTPException(status_code=400, detail=f"Схема используется в {datasets_count} датасетах")
    name = schema.name
    db.delete(schema)
    db.commit()
    log_action(db, current_admin.id, "DELETE_SCHEMA", "DATASET_SCHEMA", str(schema_id), {"name": name})
    return Response(status_code=204)

@router.post("/schemas/{schema_id}/duplicate", response_model=schemas.DatasetSchemaOut, status_code=201)
def duplicate_schema(
    schema_id: int,
    new_name: str = Query(..., description="Новое название схемы"),
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin)
):
    source_schema = db.query(models.DatasetSchema).filter(models.DatasetSchema.id == schema_id).first()
    if not source_schema:
        raise HTTPException(status_code=404, detail="Исходная схема не найдена")
    if db.query(models.DatasetSchema).filter(models.DatasetSchema.name == new_name).first():
        raise HTTPException(status_code=400, detail="Схема с таким названием уже существует")
    new_schema = models.DatasetSchema(
        name=new_name,
        columns=source_schema.columns,
        header_row_1=source_schema.header_row_1,
        header_row_2=source_schema.header_row_2,
        header_row_2_colors=source_schema.header_row_2_colors,
        created_by=current_admin.id
    )
    db.add(new_schema)
    db.commit()
    db.refresh(new_schema)
    log_action(db, current_admin.id, "DUPLICATE_SCHEMA", "DATASET_SCHEMA", str(new_schema.id),
               {"source_schema_id": schema_id, "new_name": new_name})
    return new_schema

# ======================== УПРАВЛЕНИЕ ДАТАСЕТАМИ (АДМИН) ========================
@router.get("/datasets", response_model=schemas.DatasetsListResponse)
def list_all_datasets(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    include_archived: bool = Query(True),
    owner_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin)
):
    """Администратор может видеть все датасеты с любыми фильтрами."""
    query = db.query(models.Dataset)
    if not include_archived:
        query = query.filter(models.Dataset.archived == False)
    if owner_id is not None:
        query = query.filter(models.Dataset.owner_id == owner_id)
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(models.Dataset.name.ilike(search_pattern))
    total = query.count()
    datasets = query.order_by(models.Dataset.created_at.desc()).offset(skip).limit(limit).all()
    items = [dataset_to_out(ds, db) for ds in datasets]
    return schemas.DatasetsListResponse(items=items, total=total, skip=skip, limit=limit)

@router.get("/datasets/{dataset_id}", response_model=schemas.DatasetOut)
def admin_get_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin)
):
    dataset = db.query(models.Dataset).filter(models.Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Датасет не найден")
    return dataset_to_out(dataset, db)


# ======================== СТАТИСТИКА СИСТЕМЫ ========================
@router.get("/stats", response_model=schemas.AdminStats)
def get_admin_stats(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin)
):
    total_users = db.query(models.User).count()
    active_users = db.query(models.User).filter(models.User.is_active == True).count()
    total_datasets = db.query(models.Dataset).count()
    archived_datasets = db.query(models.Dataset).filter(models.Dataset.archived == True).count()
    total_rows = db.query(models.Row).count()
    total_comments = db.query(models.CellComment).count()
    return schemas.AdminStats(
        total_users=total_users,
        active_users=active_users,
        total_datasets=total_datasets,
        archived_datasets=archived_datasets,
        total_rows=total_rows,
        total_comments=total_comments,
    )


# ======================== ЖУРНАЛ АУДИТА ========================
@router.get("/audit", response_model=schemas.AuditLogResponse)
def get_audit_log(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    user_id: Optional[int] = Query(None),
    action: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin)
):
    query = db.query(models.UserActionLog)
    if user_id is not None:
        query = query.filter(models.UserActionLog.user_id == user_id)
    if action:
        action_pattern = f"%{action}%"
        query = query.filter(models.UserActionLog.action.ilike(action_pattern))
    if entity_type:
        query = query.filter(models.UserActionLog.entity_type == entity_type)
    total = query.count()
    logs = query.order_by(models.UserActionLog.created_at.desc()).offset(skip).limit(limit).all()
    items = []
    for log in logs:
        username = None
        user = db.query(models.User).filter(models.User.id == log.user_id).first()
        if user:
            username = user.username
        items.append(schemas.AuditLogEntry(
            id=log.id,
            user_id=log.user_id,
            username=username,
            action=log.action,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            details=log.details,
            ip_address=log.ip_address,
            user_agent=log.user_agent,
            created_at=log.created_at,
        ))
    return schemas.AuditLogResponse(items=items, total=total, skip=skip, limit=limit)

@router.patch("/datasets/{dataset_id}/owner")
def change_dataset_owner(
    dataset_id: int,
    new_owner_id: int = Query(..., description="ID нового владельца"),
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin)
):
    dataset = db.query(models.Dataset).filter(models.Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Датасет не найден")
    new_owner = db.query(models.User).filter(models.User.id == new_owner_id).first()
    if not new_owner:
        raise HTTPException(status_code=404, detail="Новый владелец не найден")
    old_owner_id = dataset.owner_id
    dataset.owner_id = new_owner_id
    db.commit()
    log_action(db, current_admin.id, "CHANGE_OWNER", "DATASET", str(dataset.id),
               {"old_owner_id": old_owner_id, "new_owner_id": new_owner_id})
    return {"ok": True, "message": f"Владелец изменён на {new_owner.username} (ID {new_owner_id})"}

# ======================== СИСТЕМНЫЕ НАСТРОЙКИ ========================
@router.get("/settings", response_model=List[schemas.SystemSettingOut])
def list_settings(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin)
):
    return db.query(models.SystemSetting).order_by(models.SystemSetting.key).all()


@router.get("/settings/{key}", response_model=schemas.SystemSettingOut)
def get_setting(
    key: str,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin)
):
    setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first()
    if not setting:
        raise HTTPException(status_code=404, detail="Настройка не найдена")
    return setting


@router.put("/settings/{key}", response_model=schemas.SystemSettingOut)
def update_setting(
    key: str,
    body: schemas.SystemSettingUpdate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin)
):
    setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first()
    if not setting:
        setting = models.SystemSetting(key=key, value=body.value, description=body.description)
        db.add(setting)
    else:
        setting.value = body.value
        if body.description is not None:
            setting.description = body.description
        setting.updated_by = current_admin.id
    db.commit()
    db.refresh(setting)
    return setting


@router.delete("/settings/{key}", status_code=204)
def delete_setting(
    key: str,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin)
):
    setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first()
    if not setting:
        raise HTTPException(status_code=404, detail="Настройка не найдена")
    db.delete(setting)
    db.commit()
    return Response(status_code=204)


@router.patch("/datasets/{dataset_id}/structure", response_model=schemas.DatasetOut)
def admin_update_dataset_structure(
    dataset_id: int,
    structure: schemas.DatasetSchemaUpdate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin)
):
    """Изменение структуры колонок, строк итогов/групп (только админ)."""
    dataset = db.query(models.Dataset).filter(models.Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Датасет не найден")
    if structure.columns is not None:
        dataset.columns = [col.model_dump() if hasattr(col, 'model_dump') else col for col in structure.columns]
    if structure.header_row_1 is not None:
        dataset.header_row_1 = structure.header_row_1
    if structure.header_row_2 is not None:
        dataset.header_row_2 = structure.header_row_2
    if structure.header_row_2_colors is not None:
        dataset.header_row_2_colors = structure.header_row_2_colors
    db.commit()
    db.refresh(dataset)
    log_action(db, current_admin.id, "ADMIN_UPDATE_DATASET_STRUCTURE", "DATASET", str(dataset.id))
    return schemas.DatasetOut(
        id=dataset.id,
        name=dataset.name,
        owner_id=dataset.owner_id,
        columns=dataset.columns,
        header_row_1=dataset.header_row_1,
        header_row_2=dataset.header_row_2,
        header_row_2_colors=dataset.header_row_2_colors,
        row_filter=dataset.row_filter,
        unique_columns=dataset.unique_columns,
        default_sort_column=dataset.default_sort_column,
        default_sort_order=dataset.default_sort_order,
        schema_id=dataset.schema_id,
        archived=dataset.archived,
        created_at=dataset.created_at,
        updated_at=dataset.updated_at
    )