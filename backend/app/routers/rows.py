# backend/app/routers/rows.py

from fastapi import APIRouter, Depends, HTTPException, Query, Path, Response
from sqlalchemy.orm import Session
from typing import List, Optional, Any, Dict
from sqlalchemy import cast, String, or_, func, and_, Float
from app import models, schemas, auth, dependencies
from app.database import get_db
from app.services.audit_service import log_action, save_row_history
from app.services.validation import check_uniqueness
from fastapi_cache import FastAPICache
from fastapi_cache.decorator import cache
from app.websocket_manager import manager
import asyncio

router = APIRouter(prefix="/api/datasets/{dataset_id}/rows", tags=["rows"], redirect_slashes=False)


# ========================= ПОЛУЧЕНИЕ СПИСКА СТРОК =========================
@router.get("/")
async def get_rows(
    dataset_id: int = Path(..., description="ID датасета"),
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(50, ge=1, le=100000, description="Размер страницы"),
    sort_by: Optional[str] = Query(None, description="Колонка для сортировки"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$", description="Порядок сортировки"),
    search: Optional[str] = Query(None, max_length=100, description="Поиск по всем колонкам"),
    filter_model: Optional[str] = Query(None, description="JSON-строка filterModel от AG Grid"),
    sheet_id: Optional[str] = Query("main", description="ID листа"),
    db: Session = Depends(get_db),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=False)),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """
    Получение списка строк датасета с пагинацией, сортировкой и поиском.
    Доступные колонки для сортировки определяются структурой датасета.
    Поиск выполняется по всем текстовым колонкам.
    """
    # Получаем колонки датасета
    columns = dataset.columns or []

    # Базовый запрос
    query = db.query(models.Row).filter(models.Row.dataset_id == dataset_id, models.Row.sheet_id == sheet_id)

    # Применяем фильтр строк, если пользователь не админ
    if not auth.has_permission(current_user, "full_access", db):
        query = dependencies.apply_row_filter(query, dataset, current_user, db)

    # Поиск по всем колонкам
    if search:
        search_pattern = f"%{search}%"
        search_filter = []
        for col in columns:
            col_id = col["id"]
            # Поиск только по строковым колонкам
            if col.get("type") == "string":
                search_filter.append(
                    cast(models.Row.data[col_id].astext, String).ilike(search_pattern)
                )
        if search_filter:
            query = query.filter(or_(*search_filter))

    # Фильтр по колонкам из AG Grid filterModel
    if filter_model:
        import json
        try:
            model = json.loads(filter_model)
        except json.JSONDecodeError:
            pass
        else:
            col_map = {col["id"]: col for col in columns}
            filter_conditions = []
            for col_id, rule in model.items():
                col_def = col_map.get(col_id)
                if not col_def:
                    continue
                ft = rule.get("filterType")
                op = rule.get("type", "contains")
                val = rule.get("filter")
                if val is None:
                    continue
                col_expr = cast(models.Row.data[col_id].astext, String)
                if ft == "text":
                    str_val = str(val)
                    contains_pattern = f"%{str_val}%"
                    starts_pattern = f"{str_val}%"
                    ends_pattern = f"%{str_val}"
                    if op == "contains":
                        filter_conditions.append(col_expr.ilike(contains_pattern))
                    elif op == "notContains":
                        filter_conditions.append(~col_expr.ilike(contains_pattern))
                    elif op == "equals":
                        filter_conditions.append(col_expr == str_val)
                    elif op == "notEqual":
                        filter_conditions.append(col_expr != str_val)
                    elif op == "startsWith":
                        filter_conditions.append(col_expr.ilike(starts_pattern))
                    elif op == "endsWith":
                        filter_conditions.append(col_expr.ilike(ends_pattern))
                elif ft == "number":
                    try:
                        num_val = float(val)
                    except (ValueError, TypeError):
                        continue
                    if op == "equals":
                        filter_conditions.append(
                            cast(models.Row.data[col_id].astext, Float) == num_val
                        )
                    elif op == "notEqual":
                        filter_conditions.append(
                            cast(models.Row.data[col_id].astext, Float) != num_val
                        )
                    elif op == "lessThan":
                        filter_conditions.append(
                            cast(models.Row.data[col_id].astext, Float) < num_val
                        )
                    elif op == "lessThanOrEqual":
                        filter_conditions.append(
                            cast(models.Row.data[col_id].astext, Float) <= num_val
                        )
                    elif op == "greaterThan":
                        filter_conditions.append(
                            cast(models.Row.data[col_id].astext, Float) > num_val
                        )
                    elif op == "greaterThanOrEqual":
                        filter_conditions.append(
                            cast(models.Row.data[col_id].astext, Float) >= num_val
                        )
            if filter_conditions:
                query = query.filter(and_(*filter_conditions))

    # Сортировка
    if sort_by:
        # Проверяем существование колонки
        if any(col["id"] == sort_by for col in columns):
            sort_column = cast(models.Row.data[sort_by].astext, String)
            if sort_order == "asc":
                query = query.order_by(sort_column)
            else:
                query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(models.Row.row_order)
    else:
        # Сортировка по умолчанию
        if dataset.default_sort_column:
            if any(col["id"] == dataset.default_sort_column for col in columns):
                sort_column = cast(models.Row.data[dataset.default_sort_column].astext, String)
                order_dir = dataset.default_sort_order or "asc"
                if order_dir == "asc":
                    query = query.order_by(sort_column)
                else:
                    query = query.order_by(sort_column.desc())
            else:
                query = query.order_by(models.Row.row_order)
        else:
            query = query.order_by(models.Row.row_order)

    # Пагинация
    total = query.count()
    offset = (page - 1) * page_size
    rows = query.offset(offset).limit(page_size).all()

    return {
        "items": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size
    }


# ========================= СОЗДАНИЕ СТРОКИ =========================
@router.post("/", response_model=schemas.RowOut, status_code=201)
async def create_row(
    dataset_id: int = Path(..., description="ID датасета"),
    row: schemas.RowCreate = ...,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=True))
):
    """
    Создание новой строки в датасете.
    Проверяет права на редактирование каждой заполняемой колонки.
    Проверяет уникальность значений согласно настройкам датасета.
    """
    columns = dataset.columns or []

    # Авто-создание колонок, которых нет в структуре датасета
    cols_changed = False
    for col_id in row.data.keys():
        col_exists = any(col["id"] == col_id for col in columns)
        if not col_exists:
            new_col = {"id": col_id, "header": col_id, "type": "string", "editableBy": []}
            columns.append(new_col)
            cols_changed = True
        if not dependencies.can_edit_column(current_user, dataset, col_id, db):
            raise HTTPException(status_code=403, detail=f"Нет прав на редактирование колонки '{col_id}'")
    if cols_changed:
        dataset.columns = columns
        db.commit()

    # Проверяем уникальность
    check_uniqueness(db, dataset, None, row.data)

    # Определяем порядковый номер
    if row.row_order < 0:
        max_order = db.query(func.max(models.Row.row_order)).filter(
            models.Row.dataset_id == dataset_id
        ).scalar()
        row_order = (max_order + 1) if max_order is not None else 0
    else:
        row_order = row.row_order

    db_row = models.Row(
        dataset_id=dataset_id,
        sheet_id=row.sheet_id,
        data=row.data,
        formulas=row.formulas or {},
        row_order=row_order,
        version=1
    )

    db.add(db_row)
    db.commit()
    db.refresh(db_row)

    # Сохраняем историю
    save_row_history(db, db_row.id, dataset_id, db_row.version,
                     row.data, row.formulas or {}, current_user.id, "create")

    # Логируем создание каждой заполненной ячейки
    for col_id, value in row.data.items():
        if value is not None and value != "":
            db.add(models.CellHistory(
                dataset_id=dataset_id,
                row_id=db_row.id,
                column_id=col_id,
                old_value=None,
                new_value=str(value),
                changed_by=current_user.id
            ))
    db.commit()

    log_action(db, current_user.id, "CREATE", "ROW", str(db_row.id), {"dataset_id": dataset_id})

    # Очищаем кэш
    await FastAPICache.clear(namespace=f"dataset:{dataset_id}:rows")

    # Отправляем уведомление через WebSocket
    row_out = schemas.RowOut.model_validate(db_row).model_dump()
    asyncio.create_task(manager.broadcast(
        dataset_id,
        {"type": "row_created", "row": row_out, "user_id": current_user.id}
    ))

    return db_row


# ========================= МАССОВЫЕ ОПЕРАЦИИ =========================
@router.patch("/batch")
async def batch_update_rows(
    dataset_id: int = Path(..., description="ID датасета"),
    updates: List[schemas.RowBatchUpdate] = ...,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=True))
):
    """Массовое обновление строк."""
    columns = dataset.columns or []
    updated = 0
    errors = []

    updated_rows: list[dict] = []
    for idx, upd in enumerate(updates):
        try:
            row = db.query(models.Row).filter(
                models.Row.id == upd.id,
                models.Row.dataset_id == dataset_id
            ).first()
            if not row:
                errors.append(f"Строка {upd.id} не найдена")
                continue

            if row.version != upd.version:
                errors.append(f"Строка {upd.id}: конфликт версий")
                continue

            for col_id in upd.data.keys():
                if not dependencies.can_edit_column(current_user, dataset, col_id, db):
                    errors.append(f"Строка {upd.id}: нет прав на колонку '{col_id}'")
                    continue

            old_data = row.data.copy() if row.data else {}
            old_formulas = row.formulas.copy() if row.formulas else {}

            save_row_history(db, row.id, dataset_id, row.version,
                             old_data, old_formulas, current_user.id, "update")

            existing_data = row.data or {}
            merged_data = {k: v for k, v in existing_data.items() if k.startswith('_')}
            merged_data.update((upd.data or {}))
            row.data = merged_data
            row.formulas = upd.formulas or {}
            if upd.cell_styles is not None:
                row.cell_styles = upd.cell_styles
            if upd.row_order is not None:
                row.row_order = upd.row_order
            row.version += 1

            for col_id, new_val in upd.data.items():
                old_val = old_data.get(col_id)
                if old_val != new_val:
                    db.add(models.CellHistory(
                        dataset_id=dataset_id,
                        row_id=row.id,
                        column_id=col_id,
                        old_value=str(old_val) if old_val is not None else None,
                        new_value=str(new_val) if new_val is not None else None,
                        changed_by=current_user.id
                    ))
            updated += 1
            updated_rows.append({"id": row.id, "version": row.version})
        except HTTPException as e:
            errors.append(f"Строка {upd.id}: {e.detail}")
        except Exception as e:
            errors.append(f"Строка {upd.id}: {str(e)}")

    if errors:
        db.rollback()
        log_action(db, current_user.id, "BATCH_UPDATE", "ROW", None,
                   {"dataset_id": dataset_id, "updated": 0, "errors": len(errors)})
        return {"updated": 0, "rows": [], "errors": errors, "total_processed": len(updates)}

    db.commit()
    log_action(db, current_user.id, "BATCH_UPDATE", "ROW", None,
               {"dataset_id": dataset_id, "updated": updated, "errors": len(errors)})

    await FastAPICache.clear(namespace=f"dataset:{dataset_id}:rows")
    asyncio.create_task(manager.broadcast(
        dataset_id,
        {"type": "rows_updated", "count": updated, "user_id": current_user.id}
    ))

    return {"updated": updated, "rows": updated_rows, "errors": errors, "total_processed": len(updates)}


@router.post("/batch", status_code=201)
async def batch_create_rows(
    dataset_id: int = Path(..., description="ID датасета"),
    rows: List[schemas.RowCreate] = ...,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=True))
):
    """Массовое создание строк (например, при вставке из буфера обмена)."""
    columns = dataset.columns or []

    max_order = db.query(func.max(models.Row.row_order)).filter(
        models.Row.dataset_id == dataset_id
    ).scalar()
    next_order = (max_order + 1) if max_order is not None else 0

    created = 0
    errors = []

    created_rows: list[models.Row] = []
    for idx, row_data in enumerate(rows):
        savepoint = db.begin_nested()
        try:
            # Проверка прав и колонок
            perm_denied = False
            for col_id in row_data.data.keys():
                if not dependencies.can_edit_column(current_user, dataset, col_id, db):
                    errors.append(f"Строка {idx + 1}: нет прав на колонку '{col_id}'")
                    perm_denied = True
                    break
            if perm_denied:
                savepoint.rollback()
                continue
            check_uniqueness(db, dataset, None, row_data.data)

            row_order = row_data.row_order if row_data.row_order >= 0 else next_order + idx
            db_row = models.Row(
                dataset_id=dataset_id,
                sheet_id=row_data.sheet_id,
                data=row_data.data,
                formulas=row_data.formulas or {},
                cell_styles=row_data.cell_styles or {},
                row_order=row_order,
                version=1
            )
            db.add(db_row)
            db.flush()
            save_row_history(db, db_row.id, dataset_id, 1,
                             row_data.data, row_data.formulas or {}, current_user.id, "create")
            created_rows.append(db_row)
            created += 1
            savepoint.commit()
        except HTTPException as e:
            errors.append(f"Строка {idx + 1}: {e.detail}")
            savepoint.rollback()
        except Exception as e:
            errors.append(f"Строка {idx + 1}: {str(e)}")
            savepoint.rollback()

    db.commit()

    # Формируем ответ с ID созданных строк
    created_out = []
    for r in created_rows:
        db.refresh(r)
        created_out.append(schemas.RowOut.model_validate(r).model_dump())

    log_action(db, current_user.id, "BATCH_CREATE", "ROW", None,
               {"dataset_id": dataset_id, "created": created, "errors": len(errors)})

    await FastAPICache.clear(namespace=f"dataset:{dataset_id}:rows")
    asyncio.create_task(manager.broadcast(
        dataset_id,
        {"type": "rows_created", "count": created, "user_id": current_user.id}
    ))

    return {"created": created, "rows": created_out, "errors": errors, "total_processed": len(rows)}


@router.delete("/batch")
async def batch_delete_rows(
    dataset_id: int = Path(..., description="ID датасета"),
    row_ids: List[int] = Query(..., description="Список ID строк для удаления"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=True))
):
    """Массовое удаление строк."""
    deleted = 0
    errors = []

    for row_id in row_ids:
        row = db.query(models.Row).filter(
            models.Row.id == row_id,
            models.Row.dataset_id == dataset_id
        ).first()
        if row:
            save_row_history(db, row.id, dataset_id, row.version,
                             row.data.copy() if row.data else {},
                             row.formulas.copy() if row.formulas else {},
                             current_user.id, "delete")
            db.query(models.CellComment).filter(models.CellComment.row_id == row_id).delete()
            db.query(models.CellHistory).filter(models.CellHistory.row_id == row_id).delete()
            db.delete(row)
            deleted += 1
        else:
            errors.append(f"Строка {row_id} не найдена")

    db.commit()
    log_action(db, current_user.id, "BATCH_DELETE", "ROW", None,
               {"dataset_id": dataset_id, "deleted": deleted, "errors": errors})

    await FastAPICache.clear(namespace=f"dataset:{dataset_id}:rows")
    asyncio.create_task(manager.broadcast(
        dataset_id,
        {"type": "rows_deleted", "count": deleted, "user_id": current_user.id}
    ))

    return {"deleted": deleted, "errors": errors}


# ========================= ОБНОВЛЕНИЕ СТРОКИ =========================
@router.patch("/{row_id}", response_model=schemas.RowOut)
async def update_row(
    dataset_id: int = Path(..., description="ID датасета"),
    row_id: int = Path(..., description="ID строки"),
    update: schemas.RowUpdate = ...,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=True))
):
    """
    Обновление существующей строки.
    Проверяет версию (оптимистичная блокировка), права на редактируемые колонки, уникальность.
    Сохраняет историю строки и каждой изменённой ячейки.
    """
    columns = dataset.columns or []

    row = db.query(models.Row).filter(
        models.Row.id == row_id,
        models.Row.dataset_id == dataset_id
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Строка не найдена")

    # Оптимистичная блокировка
    if row.version != update.version:
        raise HTTPException(
            status_code=409,
            detail="Конфликт версий. Данные были изменены другим пользователем.",
            headers={"X-Current-Version": str(row.version)}
        )

    # Авто-создание колонок и проверка прав
    cols_changed = False
    for col_id in update.data.keys():
        col_exists = any(col["id"] == col_id for col in columns)
        if not col_exists:
            new_col = {"id": col_id, "header": col_id, "type": "string", "editableBy": []}
            columns.append(new_col)
            cols_changed = True
        if not dependencies.can_edit_column(current_user, dataset, col_id, db):
            raise HTTPException(status_code=403, detail=f"Нет прав на редактирование колонки '{col_id}'")
    if cols_changed:
        dataset.columns = columns
        db.commit()

    check_uniqueness(db, dataset, row.id, update.data)

    old_data = row.data.copy() if row.data else {}
    old_formulas = row.formulas.copy() if row.formulas else {}

    # Сохраняем историю строки
    save_row_history(db, row.id, dataset_id, row.version,
                     old_data, old_formulas, current_user.id, "update")

    # Обновляем данные — сохраняем ключи с префиксом _ (метаданные)
    existing_data = row.data or {}
    merged_data = {k: v for k, v in existing_data.items() if k.startswith('_')}
    merged_data.update((update.data or {}))
    row.data = merged_data
    row.formulas = update.formulas or {}
    if update.cell_styles is not None:
        row.cell_styles = update.cell_styles
    if update.row_order is not None:
        row.row_order = update.row_order
    row.version += 1

    # История ячеек
    for col_id, new_val in update.data.items():
        old_val = old_data.get(col_id)
        if old_val != new_val:
            db.add(models.CellHistory(
                dataset_id=dataset_id,
                row_id=row_id,
                column_id=col_id,
                old_value=str(old_val) if old_val is not None else None,
                new_value=str(new_val) if new_val is not None else None,
                changed_by=current_user.id
            ))

    db.commit()
    db.refresh(row)

    log_action(db, current_user.id, "UPDATE", "ROW", str(row.id),
               {"dataset_id": dataset_id, "version": row.version})

    await FastAPICache.clear(namespace=f"dataset:{dataset_id}:rows")

    row_out = schemas.RowOut.model_validate(row).model_dump()
    asyncio.create_task(manager.broadcast(
        dataset_id,
        {"type": "row_updated", "row": row_out, "user_id": current_user.id}
    ))

    return row


# ========================= УДАЛЕНИЕ СТРОКИ =========================
@router.delete("/{row_id}", status_code=204)
async def delete_row(
    dataset_id: int = Path(..., description="ID датасета"),
    row_id: int = Path(..., description="ID строки"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=True))
):
    """Удаление строки. Сохраняет историю перед удалением."""
    row = db.query(models.Row).filter(
        models.Row.id == row_id,
        models.Row.dataset_id == dataset_id
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Строка не найдена")

    # Сохраняем историю перед удалением
    save_row_history(db, row.id, dataset_id, row.version,
                     row.data.copy() if row.data else {},
                     row.formulas.copy() if row.formulas else {},
                     current_user.id, "delete")

    # Удаляем связанные комментарии и историю ячеек
    db.query(models.CellComment).filter(models.CellComment.row_id == row_id).delete()
    db.query(models.CellHistory).filter(models.CellHistory.row_id == row_id).delete()
    db.delete(row)
    db.commit()

    log_action(db, current_user.id, "DELETE", "ROW", str(row_id), {"dataset_id": dataset_id})

    await FastAPICache.clear(namespace=f"dataset:{dataset_id}:rows")
    asyncio.create_task(manager.broadcast(
        dataset_id,
        {"type": "row_deleted", "row_id": row_id, "user_id": current_user.id}
    ))

    return Response(status_code=204)


# ========================= ИСТОРИЯ СТРОКИ =========================
@router.get("/{row_id}/history")
def get_row_history(
    dataset_id: int,
    row_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=False))
):
    row = db.query(models.Row).filter(
        models.Row.id == row_id,
        models.Row.dataset_id == dataset_id
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Строка не найдена")

    history = db.query(models.RowHistory).filter(
        models.RowHistory.row_id == row_id
    ).order_by(models.RowHistory.version.desc()).all()
    return history


@router.post("/{row_id}/restore/{version}")
async def restore_row_version(
    dataset_id: int,
    row_id: int,
    version: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=True))
):
    row = db.query(models.Row).filter(
        models.Row.id == row_id,
        models.Row.dataset_id == dataset_id
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Строка не найдена")

    history_entry = db.query(models.RowHistory).filter(
        models.RowHistory.row_id == row_id,
        models.RowHistory.version == version
    ).first()
    if not history_entry:
        raise HTTPException(status_code=404, detail="Версия не найдена")

    # Сохраняем текущее состояние
    save_row_history(db, row.id, dataset_id, row.version,
                     row.data.copy() if row.data else {},
                     row.formulas.copy() if row.formulas else {},
                     current_user.id, "update")

    row.data = history_entry.data
    row.formulas = history_entry.formulas
    row.version += 1

    db.commit()
    db.refresh(row)

    log_action(db, current_user.id, "RESTORE_ROW", "ROW", str(row.id),
               {"dataset_id": dataset_id, "restored_version": version, "new_version": row.version})

    await FastAPICache.clear(namespace=f"dataset:{dataset_id}:rows")
    row_out = schemas.RowOut.model_validate(row).model_dump()
    asyncio.create_task(manager.broadcast(
        dataset_id,
        {"type": "row_updated", "row": row_out, "user_id": current_user.id}
    ))

    return {"ok": True, "new_version": row.version, "restored_from": version}


# ========================= ОБНОВЛЕНИЕ СТИЛЕЙ ЯЧЕЙКИ =========================
@router.patch("/{row_id}/cell-styles")
async def update_cell_styles(
    dataset_id: int,
    row_id: int,
    body: schemas.CellStylesUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=True))
):
    """Обновление стилей ячеек строки (шрифт, размер, цвет и т.д.)."""
    row = db.query(models.Row).filter(
        models.Row.id == row_id,
        models.Row.dataset_id == dataset_id
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Строка не найдена")

    # Сливаем с существующими стилями
    existing = row.cell_styles or {}
    for col_id, styles in body.cell_styles.items():
        if styles is None:
            existing.pop(col_id, None)
        else:
            existing[col_id] = styles
    row.cell_styles = existing

    # Сохраняем метаданные (_numberFormats, _dropdowns и т.д.) в row.data
    if body.metadata:
        if not row.data:
            row.data = {}
        for meta_key, meta_val in body.metadata.items():
            if meta_val is None:
                row.data.pop(meta_key, None)
            elif isinstance(meta_val, dict):
                existing_meta = row.data.get(meta_key, {})
                if not isinstance(existing_meta, dict):
                    existing_meta = {}
                existing_meta.update(meta_val)
                row.data[meta_key] = existing_meta
            else:
                row.data[meta_key] = meta_val

    db.commit()

    log_action(db, current_user.id, "UPDATE_CELL_STYLES", "ROW", str(row.id),
               {"dataset_id": dataset_id})

    await FastAPICache.clear(namespace=f"dataset:{dataset_id}:rows")
    asyncio.create_task(manager.broadcast(
        dataset_id,
        {"type": "cell_styles_updated", "row_id": row_id, "cell_styles": existing, "user_id": current_user.id}
    ))

    return {"ok": True, "cell_styles": existing}


# ========================= ИСТОРИЯ ЯЧЕЙКИ =========================
@router.get("/{row_id}/cells/{column_id}/history", response_model=List[schemas.CellHistoryOut])
def get_cell_history(
    dataset_id: int,
    row_id: int,
    column_id: str,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=False))
):
    row = db.query(models.Row).filter(
        models.Row.id == row_id,
        models.Row.dataset_id == dataset_id
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Строка не найдена")

    # Проверка существования колонки
    if not any(col["id"] == column_id for col in dataset.columns):
        raise HTTPException(status_code=404, detail=f"Колонка '{column_id}' не найдена")

    history = db.query(models.CellHistory).filter(
        models.CellHistory.dataset_id == dataset_id,
        models.CellHistory.row_id == row_id,
        models.CellHistory.column_id == column_id
    ).order_by(models.CellHistory.changed_at.desc()).limit(limit).all()

    return history


# ========================= ОБНОВЛЕНИЕ ОТДЕЛЬНОЙ ЯЧЕЙКИ =========================
@router.patch("/{row_id}/cells/{column_id}")
async def update_cell(
    dataset_id: int,
    row_id: int,
    column_id: str,
    body: schemas.CellUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=True))
):
    """Обновление значения отдельной ячейки (быстрое редактирование)."""
    # Авто-создание колонки, если её нет в структуре датасета
    columns = dataset.columns or []
    col_exists = any(col["id"] == column_id for col in columns)
    if not col_exists:
        new_col = {"id": column_id, "header": column_id, "type": "string", "editableBy": []}
        dataset.columns = columns + [new_col]
        db.commit()

    if not dependencies.can_edit_column(current_user, dataset, column_id, db):
        raise HTTPException(status_code=403, detail=f"Нет прав на редактирование колонки '{column_id}'")

    row = db.query(models.Row).filter(
        models.Row.id == row_id,
        models.Row.dataset_id == dataset_id
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Строка не найдена")

    # Оптимистичная блокировка
    if body.expected_version is not None and row.version != body.expected_version:
        raise HTTPException(
            status_code=409,
            detail="Конфликт версий. Данные были изменены другим пользователем.",
            headers={"X-Current-Version": str(row.version)}
        )

    old_value = row.data.get(column_id) if row.data else None
    if str(old_value) == body.value and (body.formula is None or row.formulas.get(column_id) == body.formula):
        return {"ok": True, "message": "Значение не изменилось"}

    check_uniqueness(db, dataset, row.id, {column_id: body.value})

    # История строки
    save_row_history(db, row.id, dataset_id, row.version,
                     row.data.copy() if row.data else {},
                     row.formulas.copy() if row.formulas else {},
                     current_user.id, "update")

    if not row.data:
        row.data = {}
    row.data[column_id] = body.value
    # Сохраняем метаданные (_numberFormats, _dropdowns и т.д.)
    if body.metadata:
        for meta_key, meta_val in body.metadata.items():
            if meta_val is None:
                row.data.pop(meta_key, None)
            elif isinstance(meta_val, dict):
                existing_meta = row.data.get(meta_key, {})
                if not isinstance(existing_meta, dict):
                    existing_meta = {}
                existing_meta.update(meta_val)
                row.data[meta_key] = existing_meta
            else:
                row.data[meta_key] = meta_val
    if body.formula is not None:
        if not row.formulas:
            row.formulas = {}
        row.formulas[column_id] = body.formula
    else:
        if row.formulas and column_id in row.formulas:
            del row.formulas[column_id]
    row.version += 1

    # История ячейки
    db.add(models.CellHistory(
        dataset_id=dataset_id,
        row_id=row_id,
        column_id=column_id,
        old_value=str(old_value) if old_value is not None else None,
        new_value=body.value,
        changed_by=current_user.id
    ))

    db.commit()
    db.refresh(row)

    log_action(db, current_user.id, "UPDATE_CELL", "ROW", str(row.id),
               {"dataset_id": dataset_id, "column": column_id})

    await FastAPICache.clear(namespace=f"dataset:{dataset_id}:rows")
    asyncio.create_task(manager.broadcast(
        dataset_id,
        {
            "type": "cell_updated",
            "row_id": row_id,
            "column_id": column_id,
            "value": body.value,
            "version": row.version,
            "formula": body.formula,
            "user_id": current_user.id,
        }
    ))

    return {"ok": True, "row_id": row_id, "column_id": column_id, "value": body.value, "version": row.version, "formula": body.formula}


# ========================= КОПИРОВАНИЕ СТРОКИ =========================
@router.post("/{row_id}/duplicate", response_model=schemas.RowOut, status_code=201)
async def duplicate_row(
    dataset_id: int,
    row_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=True))
):
    """Создание копии существующей строки."""
    source_row = db.query(models.Row).filter(
        models.Row.id == row_id,
        models.Row.dataset_id == dataset_id
    ).first()
    if not source_row:
        raise HTTPException(status_code=404, detail="Строка не найдена")

    max_order = db.query(func.max(models.Row.row_order)).filter(
        models.Row.dataset_id == dataset_id
    ).scalar()
    row_order = (max_order + 1) if max_order is not None else 0

    new_row = models.Row(
        dataset_id=dataset_id,
        data=source_row.data.copy() if source_row.data else {},
        formulas=source_row.formulas.copy() if source_row.formulas else {},
        row_order=row_order,
        version=1
    )
    db.add(new_row)
    db.commit()
    db.refresh(new_row)

    save_row_history(db, new_row.id, dataset_id, 1,
                     new_row.data, new_row.formulas or {}, current_user.id, "create")
    log_action(db, current_user.id, "DUPLICATE_ROW", "ROW", str(new_row.id),
               {"dataset_id": dataset_id, "source_row_id": row_id})

    await FastAPICache.clear(namespace=f"dataset:{dataset_id}:rows")
    row_out = schemas.RowOut.model_validate(new_row).model_dump()
    asyncio.create_task(manager.broadcast(
        dataset_id,
        {"type": "row_created", "row": row_out, "user_id": current_user.id}
    ))

    return new_row