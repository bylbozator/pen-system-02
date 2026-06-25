# backend/app/services/audit_service.py

from sqlalchemy.orm import Session
from app import models


def log_action(
    db: Session,
    user_id: int,
    action: str,
    entity_type: str,
    entity_id: str,
    details: dict,
    ip_address: str = "",
    user_agent: str = ""
):
    log_entry = models.UserActionLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        details=details,
        ip_address=ip_address,
        user_agent=user_agent
    )
    db.add(log_entry)


def save_row_history(
    db: Session,
    row_id: int,
    dataset_id: int,      # <-- было sheet_id, теперь dataset_id
    version: int,
    data: dict,
    formulas: dict,
    user_id: int,
    change_type: str
):
    history = models.RowHistory(
        row_id=row_id,
        dataset_id=dataset_id,  # <-- изменено
        version=version,
        data=data,
        formulas=formulas,
        changed_by=user_id,
        change_type=change_type
    )
    db.add(history)