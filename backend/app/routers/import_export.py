from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session
from fastapi.responses import Response
from urllib.parse import quote
from typing import List, Optional
from io import BytesIO
import structlog
import magic

from app import models, auth
from app.database import get_db
from app.services.multi_format_import_service import detect_format

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/import-export",
    tags=["import_export"],
    redirect_slashes=False,
)

MAX_PREVIEW_FILE_SIZE = 50 * 1024 * 1024
MAX_IMPORT_FILE_SIZE = 100 * 1024 * 1024

ALLOWED_MIME_TYPES = {
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # .xlsx
    'application/vnd.ms-excel',  # .xls
    'text/csv',
    'text/tab-separated-values',
    'application/vnd.oasis.opendocument.spreadsheet',  # .ods
    'application/zip',           # some systems detect xlsx as zip
    'application/octet-stream',  # fallback for some envs
}


def validate_file_mime(contents: bytes, filename: str):
    mime = magic.from_buffer(contents, mime=True)
    logger.info("File upload MIME check", filename=filename, mime=mime)
    if mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Недопустимый тип файла: {mime}. Разрешены: Excel (.xlsx, .xls), CSV, TSV, ODS"
        )


# ======================== ПРЕДПРОСМОТР (синхронно, т.к. легковесный) ========================
@router.post("/preview")
async def preview_import(
    file: UploadFile = File(...),
    header_row_index: int = Query(0, description="Индекс строки с заголовками (0-based, -1 = нет заголовков)"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    if not auth.has_permission(current_user, "can_create_datasets", db) and \
       not auth.has_permission(current_user, "full_access", db):
        raise HTTPException(status_code=403, detail="Недостаточно прав для импорта")

    if file.size and file.size > MAX_PREVIEW_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"Файл слишком большой для предпросмотра (макс {MAX_PREVIEW_FILE_SIZE // (1024*1024)} МБ)")

    contents = await file.read()
    fmt = detect_format(file.filename or "")
    try:
        if fmt == 'xlsx':
            from app.services.excel_import_service import preview_excel_sheets
            sheets_info = preview_excel_sheets(contents, preview_rows=10, header_row_index=header_row_index)
        else:
            validate_file_mime(contents, file.filename or "file.xlsx")
            from app.services.multi_format_import_service import preview_file as preview_any_file
            sheets_info = preview_any_file(contents, file.filename or "file", header_row_index=header_row_index, preview_rows=10)
        return {"sheets": sheets_info}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Preview failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка чтения файла: {str(e)}")


# ======================== ИМПОРТ (синхронно) ========================
@router.post("/import", status_code=201)
async def import_excel(
    file: UploadFile = File(...),
    sheet_names: Optional[List[str]] = Query(None, description="Список имён листов для импорта"),
    header_row_index: int = Query(0, description="Индекс строки с заголовками (0-based)"),
    create_mode: str = Query("new", description="new - создать новые датасеты, replace - заменить данные в существующих"),
    target_dataset_ids: Optional[List[int]] = Query(None, description="ID датасетов для замены (только при create_mode=replace)"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    if not auth.has_permission(current_user, "can_create_datasets", db) and \
       not auth.has_permission(current_user, "full_access", db):
        raise HTTPException(status_code=403, detail="Недостаточно прав для импорта")

    if file.size and file.size > MAX_IMPORT_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"Файл слишком большой (макс {MAX_IMPORT_FILE_SIZE // (1024*1024)} МБ)")

    if create_mode == "replace" and not target_dataset_ids:
        raise HTTPException(status_code=400, detail="Для режима replace необходимо указать target_dataset_ids (один ID)")

    contents = await file.read()
    fmt = detect_format(file.filename or "import.xlsx")

    if fmt != 'xlsx':
        validate_file_mime(contents, file.filename or "import.xlsx")

    if not sheet_names and fmt == 'xlsx':
        import openpyxl
        wb = openpyxl.load_workbook(BytesIO(contents), read_only=True, data_only=True)
        sheet_names = wb.sheetnames
        wb.close()

    if fmt == 'xlsx':
        from app.services.excel_import_service import import_sheets_as_datasets
        result = import_sheets_as_datasets(
            db=db,
            user_id=current_user.id,
            file_bytes=contents,
            sheet_names=sheet_names or [],
            header_row_index=header_row_index,
            create_mode=create_mode,
            target_dataset_ids=target_dataset_ids,
            filename=file.filename,
        )
    else:
        from app.services.multi_format_import_service import import_file_as_datasets
        result = import_file_as_datasets(
            db=db,
            user_id=current_user.id,
            file_bytes=contents,
            filename=file.filename or "import.xlsx",
            sheet_names=sheet_names,
            header_row_index=header_row_index,
            create_mode=create_mode,
            target_dataset_ids=target_dataset_ids,
        )

    return result


# ======================== ЭКСПОРТ (синхронно) ========================
@router.get("/export/{dataset_id}")
async def export_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    dataset = db.query(models.Dataset).filter(models.Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Датасет не найден")

    if dataset.owner_id != current_user.id and not auth.has_permission(current_user, "can_view_all_datasets", db) and \
       not auth.has_permission(current_user, "full_access", db):
        raise HTTPException(status_code=403, detail="Недостаточно прав для просмотра")

    from app.services.excel_export_service import export_dataset_to_excel

    try:
        excel_data = export_dataset_to_excel(db, dataset_id)
        filename = f"dataset_{dataset_id}.xlsx"
        encoded_filename = quote(filename)
        return Response(
            content=excel_data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{encoded_filename}"
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Export failed", dataset_id=dataset_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Ошибка экспорта: {str(e)}")
