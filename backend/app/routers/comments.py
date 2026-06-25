# backend/app/routers/comments.py

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app import models, schemas, auth, dependencies
from app.database import get_db
from app.services.audit_service import log_action


def _enrich_comment(comment, db):
    """Add created_by_name to a CellComment instance or list."""
    if comment is None:
        return None
    comments = comment if isinstance(comment, list) else [comment]
    user_ids = {c.created_by for c in comments if c.created_by}
    users = {u.id: u for u in db.query(models.User).filter(models.User.id.in_(user_ids)).all()} if user_ids else {}
    for c in comments:
        u = users.get(c.created_by)
        c.created_by_name = (u.last_name or "") + " " + (u.first_name or "") if u else None
        name_parts = []
        if u and u.last_name:
            name_parts.append(u.last_name)
        if u and u.first_name:
            name_parts.append(u.first_name)
        c.created_by_name = " ".join(name_parts) if name_parts else (u.username if u else None)
    return comment if isinstance(comment, list) else comment[0]


router = APIRouter(
    prefix="/api/datasets/{dataset_id}/comments",
    tags=["comments"],
    redirect_slashes=False,
)


@router.get("/all", response_model=List[schemas.CellCommentOut])
def get_all_comments(
    dataset_id: int = Path(...),
    sub_unit_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=False)),
):
    """Получить все комментарии для датасета."""
    q = db.query(models.CellComment).filter(
        models.CellComment.dataset_id == dataset_id
    )
    if sub_unit_id:
        q = q.filter(models.CellComment.sub_unit_id == sub_unit_id)
    comments = q.order_by(models.CellComment.created_at).all()
    _enrich_comment(comments, db)
    return comments


@router.get("/{row_id}/{column_id}", response_model=List[schemas.CellCommentOut])
def get_comments_for_cell(
    dataset_id: int = Path(...),
    row_id: int = Path(...),
    column_id: str = Path(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=False)),
):
    """Получить все комментарии для заданной ячейки (по row_id / column_id)."""
    comments = (
        db.query(models.CellComment)
        .filter(
            models.CellComment.dataset_id == dataset_id,
            models.CellComment.row_id == row_id,
            models.CellComment.column_id == column_id,
        )
        .order_by(models.CellComment.created_at)
        .all()
    )
    _enrich_comment(comments, db)
    return comments


@router.post("/", response_model=schemas.CellCommentOut, status_code=201)
def create_comment(
    dataset_id: int = Path(...),
    comment_data: schemas.CellCommentCreate = ...,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=True)),
):
    """Создать новый комментарий к ячейке."""
    if comment_data.row_id:
        row = (
            db.query(models.Row)
            .filter(
                models.Row.id == comment_data.row_id,
                models.Row.dataset_id == dataset_id,
            )
            .first()
        )
        if not row:
            raise HTTPException(status_code=404, detail="Строка не найдена")

    db_comment = models.CellComment(
        dataset_id=dataset_id,
        row_id=comment_data.row_id,
        column_id=comment_data.column_id or "",
        comment=comment_data.comment,
        created_by=current_user.id,
        ref=comment_data.ref,
        thread_id=comment_data.thread_id,
        row_index=comment_data.row_index,
        col_index=comment_data.col_index,
        parent_id=comment_data.parent_id,
        sub_unit_id=comment_data.sub_unit_id or "main",
    )
    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)

    log_action(
        db,
        current_user.id,
        "CREATE",
        "COMMENT",
        str(db_comment.id),
        {
            "dataset_id": dataset_id,
            "row_id": comment_data.row_id,
            "column_id": comment_data.column_id,
        },
    )
    _enrich_comment(db_comment, db)
    return db_comment


@router.patch("/{comment_id}", response_model=schemas.CellCommentOut)
def update_comment(
    dataset_id: int = Path(...),
    comment_id: int = Path(...),
    comment_update: schemas.CellCommentUpdate = ...,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=True)),
):
    """Обновить комментарий (текст или статус resolved)."""
    comment = (
        db.query(models.CellComment)
        .filter(
            models.CellComment.id == comment_id,
            models.CellComment.dataset_id == dataset_id,
        )
        .first()
    )
    if not comment:
        raise HTTPException(status_code=404, detail="Комментарий не найден")

    if comment.created_by != current_user.id and not auth.has_permission(
        current_user, "full_access", db
    ):
        raise HTTPException(
            status_code=403, detail="Не разрешено редактировать этот комментарий"
        )

    if comment_update.comment is not None:
        comment.comment = comment_update.comment

    if comment_update.resolved is not None:
        comment.resolved = comment_update.resolved
        if comment_update.resolved:
            comment.resolved_by = current_user.id
            comment.resolved_at = datetime.now()
        else:
            comment.resolved_by = None
            comment.resolved_at = None

    for field in ("ref", "thread_id", "row_index", "col_index", "sub_unit_id"):
        val = getattr(comment_update, field, None)
        if val is not None:
            setattr(comment, field, val)

    db.commit()
    db.refresh(comment)

    log_action(
        db,
        current_user.id,
        "UPDATE",
        "COMMENT",
        str(comment.id),
        {"resolved": comment.resolved},
    )
    _enrich_comment(comment, db)
    return comment


@router.delete("/{comment_id}", status_code=204)
def delete_comment(
    dataset_id: int = Path(...),
    comment_id: int = Path(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=True)),
):
    """Удалить комментарий."""
    comment = (
        db.query(models.CellComment)
        .filter(
            models.CellComment.id == comment_id,
            models.CellComment.dataset_id == dataset_id,
        )
        .first()
    )
    if not comment:
        raise HTTPException(status_code=404, detail="Комментарий не найден")

    if comment.created_by != current_user.id and not auth.has_permission(
        current_user, "full_access", db
    ):
        raise HTTPException(
            status_code=403, detail="Не разрешено удалять этот комментарий"
        )

    db.delete(comment)
    db.commit()

    log_action(db, current_user.id, "DELETE", "COMMENT", str(comment_id), {})
    return Response(status_code=204)
