from sqlalchemy.orm import Session
from fastapi import HTTPException
from app import models


def check_uniqueness(
    db: Session,
    dataset: models.Dataset,       # было sheet: models.Sheet
    row_id: int | None,
    data: dict,
):
    if not dataset.unique_columns:
        return

    unique_rules = dataset.unique_columns
    if not isinstance(unique_rules, list):
        return

    for rule in unique_rules:
        if isinstance(rule, str):
            col_id = rule
            value = data.get(col_id)
            if value is None:
                continue

            query = db.query(models.Row).filter(
                models.Row.dataset_id == dataset.id,   # sheet.id заменён
                models.Row.data[col_id].astext == str(value),
            )
            if row_id is not None:
                query = query.filter(models.Row.id != row_id)
            if query.first():
                raise HTTPException(
                    status_code=409,
                    detail=f"Значение '{value}' в колонке '{col_id}' уже существует",
                )

        elif isinstance(rule, list) and len(rule) > 0:
            values = []
            for col_id in rule:
                val = data.get(col_id)
                if val is None:
                    break
                values.append(str(val))
            else:
                conditions = [
                    models.Row.data[col_id].astext == str(data[col_id])
                    for col_id in rule
                ]
                query = db.query(models.Row).filter(
                    models.Row.dataset_id == dataset.id,   # sheet.id заменён
                    *conditions,
                )
                if row_id is not None:
                    query = query.filter(models.Row.id != row_id)
                if query.first():
                    cols_str = " + ".join(rule)
                    vals_str = " + ".join(str(data[col]) for col in rule)
                    raise HTTPException(
                        status_code=409,
                        detail=f"Комбинация '{vals_str}' в колонках [{cols_str}] уже существует",
                    )