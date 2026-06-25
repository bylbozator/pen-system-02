import base64
import structlog
from celery import shared_task
from app.database import SessionLocal
from app.services.excel_export_service import export_dataset_to_excel

logger = structlog.get_logger()


@shared_task(bind=True, name="export_dataset")
def export_dataset_task(self, dataset_id: int):
    db = SessionLocal()
    try:
        excel_data = export_dataset_to_excel(db, dataset_id)
        return {"dataset_id": dataset_id, "file_b64": base64.b64encode(excel_data).decode()}
    except Exception as e:
        logger.error("Export task failed", dataset_id=dataset_id, error=str(e))
        raise
    finally:
        db.close()
