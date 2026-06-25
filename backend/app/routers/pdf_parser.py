from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from typing import Optional
import base64
import structlog
import magic

from app import models, auth
from app.database import get_db
from app.celery_app import celery_app

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/pdf",
    tags=["pdf"],
    redirect_slashes=False,
)

MAX_PDF_FILE_SIZE = 20 * 1024 * 1024

ALLOWED_PDF_MIME = {'application/pdf'}


def validate_pdf_mime(contents: bytes, filename: str):
    mime = magic.from_buffer(contents, mime=True)
    if mime not in ALLOWED_PDF_MIME:
        raise HTTPException(
            status_code=400,
            detail=f"Недопустимый тип файла: {mime}. Ожидается PDF"
        )


@router.post("/parse")
async def parse_pdf(
    file: UploadFile = File(...),
    keywords: Optional[str] = Query(None, description="Ключевые слова через запятую"),
    db=Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    if not auth.has_permission(current_user, "can_create_datasets", db) and \
       not auth.has_permission(current_user, "full_access", db):
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    if file.size and file.size > MAX_PDF_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"Файл слишком большой (макс {MAX_PDF_FILE_SIZE // (1024*1024)} МБ)")

    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Файл должен быть в формате PDF")

    contents = await file.read()
    validate_pdf_mime(contents, file.filename or "file.pdf")
    file_b64 = base64.b64encode(contents).decode()
    keyword_list = [kw.strip() for kw in keywords.split(',') if kw.strip()] if keywords else None

    task = celery_app.send_task("parse_pdf", args=[file_b64, keyword_list])

    return {"task_id": task.id, "status": "processing"}


@router.post("/parse-invoice")
async def parse_invoice(
    file: UploadFile = File(...),
    db=Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    if not auth.has_permission(current_user, "can_create_datasets", db) and \
       not auth.has_permission(current_user, "full_access", db):
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    if file.size and file.size > MAX_PDF_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"Файл слишком большой (макс {MAX_PDF_FILE_SIZE // (1024*1024)} МБ)")

    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Файл должен быть в формате PDF")

    contents = await file.read()
    validate_pdf_mime(contents, file.filename or "file.pdf")
    file_b64 = base64.b64encode(contents).decode()

    task = celery_app.send_task("parse_invoice", args=[file_b64])

    return {"task_id": task.id, "status": "processing"}
