# backend/app/dependencies.py

from fastapi import Depends, HTTPException, status, Path
from sqlalchemy.orm import Session
from sqlalchemy import false as sa_false
from app import models, auth
from app.database import get_db


def require_permission(permission: str):
    """
    Возвращает зависимость, которая проверяет наличие у текущего
    пользователя указанного права.
    """
    async def dependency(
        current_user: models.User = Depends(auth.get_current_active_user),
        db: Session = Depends(get_db),
    ):
        if not auth.has_permission(current_user, permission, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав",
            )
        return current_user

    return dependency


def require_dataset_access(write: bool = False):
    async def dependency(
        dataset_id: int = Path(...),
        current_user: models.User = Depends(auth.get_current_active_user),
        db: Session = Depends(get_db),
    ):
        dataset = db.query(models.Dataset).filter(models.Dataset.id == dataset_id).first()
        if not dataset:
            raise HTTPException(status_code=404, detail="Датасет не найден")

        if write and dataset.archived:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Датасет находится в архиве",
            )

        if auth.has_permission(current_user, "full_access", db) or \
           auth.has_permission(current_user, "can_view_all_datasets", db):
            return dataset

        if dataset.owner_id == current_user.id:
            return dataset

        if write:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав для редактирования этого датасета",
            )

        if auth.has_permission(current_user, "can_view_datasets", db):
            return dataset

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для просмотра этого датасета",
        )

    return dependency


def can_edit_column(
    user: models.User,
    dataset: models.Dataset,
    column_id: str,
    db: Session,
) -> bool:
    """
    Проверяет, может ли пользователь редактировать конкретную колонку.
    - full_access или can_edit_all_datasets – может всё.
    - Владелец датасета – может всё.
    - Иначе проверяется список editableBy в определении колонки.
    """
    if auth.has_permission(user, "full_access", db) or \
       auth.has_permission(user, "can_edit_all_datasets", db):
        return True
    if dataset.owner_id == user.id:
        return True

    # Ищем колонку в dataset.columns
    for col in dataset.columns or []:
        if col.get("id") == column_id:
            allowed_roles = col.get("editableBy", [])
            if not allowed_roles:
                # Пустой список = нет ограничений, любой может редактировать
                return True
            user_role = user.role.name if user.role else None
            return user_role in allowed_roles

    # Колонка не найдена – создаём автоматически при сохранении
    return True


def apply_row_filter(
    query,
    dataset: models.Dataset,
    user: models.User,
    db: Session,
):
    """
    Применяет row_filter датасета (если задан) для ограничения видимых строк.
    Поддерживаются фильтры по роли, user_id, отделу.
    """
    if not dataset.row_filter:
        return query

    filter_col_id = dataset.row_filter.get("column_id")
    filter_type = dataset.row_filter.get("type", "equal")
    if not filter_col_id:
        return query

    user_value = None
    if filter_type == "role":
        user_value = user.role.name if user.role else None
    elif filter_type == "user_id":
        user_value = str(user.id)
    elif filter_type == "department":
        user_value = getattr(user, "department", None)
    else:
        # если указан какой-то другой тип, пытаемся взять атрибут пользователя
        user_value = getattr(user, filter_type, None)

    if user_value is None:
        # Нет значения – возвращаем пустой результат
        return query.filter(sa_false())

    return query.filter(models.Row.data[filter_col_id].astext == str(user_value))