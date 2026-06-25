import base64
import structlog
from celery import shared_task
from app.database import SessionLocal
from app.services.excel_import_service import import_sheets_as_datasets
from app.services.multi_format_import_service import (
    import_file_as_datasets,
    preview_file as preview_any_file,
    detect_format,
)
from app.services.excel_import_service import preview_excel_sheets
import openpyxl
from io import BytesIO

logger = structlog.get_logger()


@shared_task(bind=True, name="import_file")
def import_file_task(
    self,
    file_b64: str,
    filename: str,
    user_id: int,
    sheet_names=None,
    header_row_index: int = 0,
    create_mode: str = "new",
    target_dataset_ids=None,
):
    db = SessionLocal()
    try:
        file_bytes = base64.b64decode(file_b64)
        fmt = detect_format(filename)

        if not sheet_names and fmt == 'xlsx':
            wb = openpyxl.load_workbook(BytesIO(file_bytes), read_only=True, data_only=True)
            sheet_names = wb.sheetnames
            wb.close()

        if fmt == 'xlsx':
            result = import_sheets_as_datasets(
                db=db,
                user_id=user_id,
                file_bytes=file_bytes,
                sheet_names=sheet_names or [],
                header_row_index=header_row_index,
                create_mode=create_mode,
                target_dataset_ids=target_dataset_ids,
            )
        else:
            result = import_file_as_datasets(
                db=db,
                user_id=user_id,
                file_bytes=file_bytes,
                filename=filename,
                sheet_names=sheet_names,
                header_row_index=header_row_index,
                create_mode=create_mode,
                target_dataset_ids=target_dataset_ids,
            )
        return result
    except Exception as e:
        logger.error("Import task failed", error=str(e))
        raise
    finally:
        db.close()


@shared_task(bind=True, name="preview_file")
def preview_file_task(
    self,
    file_b64: str,
    filename: str,
    header_row_index: int = 0,
    preview_rows: int = 10,
):
    try:
        file_bytes = base64.b64decode(file_b64)
        fmt = detect_format(filename)
        if fmt in ('xlsx',):
            sheets_info = preview_excel_sheets(file_bytes, preview_rows=preview_rows, header_row_index=header_row_index)
        else:
            sheets_info = preview_any_file(file_bytes, filename, header_row_index=header_row_index, preview_rows=preview_rows)
        return {"sheets": sheets_info}
    except Exception as e:
        logger.error("Preview task failed", error=str(e))
        raise
