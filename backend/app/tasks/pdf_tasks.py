import base64
import structlog
from celery import shared_task
from app.services.pdf_parser_service import extract_structured_data, extract_invoice_records, extract_text_from_pdf

logger = structlog.get_logger()


@shared_task(bind=True, name="parse_pdf")
def parse_pdf_task(self, file_b64: str, keywords: list = None):
    try:
        file_bytes = base64.b64decode(file_b64)
        result = extract_structured_data(file_bytes, keywords=keywords)
        return result
    except Exception as e:
        logger.error("PDF parse task failed", error=str(e))
        raise


@shared_task(bind=True, name="parse_invoice")
def parse_invoice_task(self, file_b64: str):
    try:
        file_bytes = base64.b64decode(file_b64)
        text = extract_text_from_pdf(file_bytes)
        records = extract_invoice_records(text)
        return {
            "text": text,
            "text_length": len(text),
            "records_count": len(records),
            "records": records,
        }
    except Exception as e:
        logger.error("Invoice parse task failed", error=str(e))
        raise
