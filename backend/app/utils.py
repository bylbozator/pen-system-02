from typing import Optional

from sqlalchemy.orm import Session

from app import models, schemas


def _get_owner_name(db: Session, owner_id: int) -> Optional[str]:
    if not owner_id:
        return None
    owner = db.query(models.User).filter(models.User.id == owner_id).first()
    if not owner:
        return None
    name_parts = [p for p in [owner.last_name, owner.first_name] if p]
    return " ".join(name_parts) if name_parts else owner.username


def dataset_to_out(dataset: models.Dataset, db: Session = None) -> schemas.DatasetOut:
    sub_sheets = dataset.sub_sheets
    if not sub_sheets:
        sub_sheets = [{"id": "main", "name": "Лист1", "order": 0}]
    owner_name = _get_owner_name(db, dataset.owner_id) if db else None
    return schemas.DatasetOut(
        id=dataset.id,
        name=dataset.name,
        owner_id=dataset.owner_id,
        owner_name=owner_name,
        columns=dataset.columns,
        header_row_1=dataset.header_row_1,
        header_row_2=dataset.header_row_2,
        header_row_2_colors=dataset.header_row_2_colors,
        row_filter=dataset.row_filter,
        unique_columns=dataset.unique_columns,
        default_sort_column=dataset.default_sort_column,
        default_sort_order=dataset.default_sort_order,
        schema_id=dataset.schema_id,
        styles=dataset.styles,
        sub_sheets=[schemas.ListDef(**s) for s in sub_sheets],
        archived=dataset.archived,
        created_at=dataset.created_at,
        updated_at=dataset.updated_at,
    )


def user_to_out(user: models.User) -> schemas.UserOut:
    return schemas.UserOut(
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
        department=user.department,
    )
