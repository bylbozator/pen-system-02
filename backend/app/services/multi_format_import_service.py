# backend/app/services/multi_format_import_service.py
# Импорт CSV, TSV, ODS, .xls (расширение поддержки форматов)

import csv
import io
import os
import uuid
import tempfile
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

import structlog
from sqlalchemy.orm import Session

from app import models

logger = structlog.get_logger()


def _safe_unlink(path: str):
    try:
        os.unlink(path)
    except Exception:
        pass


def detect_format(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext == '.csv':
        return 'csv'
    if ext == '.tsv':
        return 'tsv'
    if ext == '.ods':
        return 'ods'
    if ext in ('.xls', '.xlsx'):
        return ext.lstrip('.')
    return 'unknown'


def _normalize_value(val) -> str:
    if val is None:
        return ""
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, (int, float)):
        return str(val)
    return str(val)


def _build_columns_from_headers(headers: List[str], sample_data: List[List[str]]) -> List[Dict[str, Any]]:
    import string

    def excel_style(col_idx: int) -> str:
        result = ""
        col_idx += 1
        while col_idx > 0:
            col_idx, remainder = divmod(col_idx - 1, 26)
            result = string.ascii_uppercase[remainder] + result
        return result

    columns = []
    for col_idx, header in enumerate(headers):
        col_id = excel_style(col_idx)
        col_type = "string"
        # Try to detect type from sample data
        non_empty = []
        for row in sample_data:
            if col_idx < len(row) and row[col_idx] and row[col_idx].strip():
                non_empty.append(row[col_idx].strip())
        if non_empty:
            all_nums = all(_is_number(v) for v in non_empty)
            all_dates = all(_is_date(v) for v in non_empty)
            if all_nums:
                col_type = "number"
            elif all_dates:
                col_type = "date"
        columns.append({
            "id": col_id,
            "header": str(header).strip() if header else col_id,
            "type": col_type,
            "editableBy": [],
            "colorGroup": None,
        })
    return columns


def _is_number(s: str) -> bool:
    if s is None:
        return False
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False


def _is_date(s: str) -> bool:
    if s is None:
        return False
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            datetime.strptime(s, fmt)
            return True
        except ValueError:
            continue
    return False


def _auto_generate_headers(max_cols: int) -> List[str]:
    import string
    result = []
    for i in range(max_cols):
        label = ""
        n = i
        while True:
            label = string.ascii_uppercase[n % 26] + label
            n = n // 26 - 1
            if n < 0:
                break
        result.append(label)
    return result


# =====================================================================
# CSV Reader
# =====================================================================
def read_csv(file_bytes: bytes, encoding: str = 'utf-8-sig', delimiter: str = ',') -> Tuple[List[str], List[List[str]]]:
    """Returns (headers, rows) from CSV data."""
    text = file_bytes.decode(encoding, errors='replace')
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = []
    for row in reader:
        rows.append([_normalize_value(cell) for cell in row])
    if not rows:
        return [], []
    # Filter out empty trailing columns
    max_cols = max(len(r) for r in rows) if rows else 0
    normalized = []
    for r in rows:
        while len(r) < max_cols:
            r.append("")
        normalized.append(r[:max_cols])
    return normalized[0], normalized[1:]


# =====================================================================
# ODS Reader (via odfpy)
# =====================================================================
def read_ods(file_bytes: bytes) -> Dict[str, Tuple[List[str], List[List[str]]]]:
    """Returns {sheet_name: (headers, rows)} from ODS file."""
    try:
        from odf.opendocument import load
        from odf.table import Table, TableRow, TableCell
        from odf.text import P
    except ImportError:
        raise ValueError("odfpy не установлен. Установите: pip install odfpy")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".ods")
    tmp_path = tmp.name
    try:
        tmp.write(file_bytes)
        tmp.flush()
        tmp.close()

        doc = load(tmp_path)
        result = {}
        for table in doc.getElementsByType(Table):
            sheet_name = table.getAttribute('name') or "Лист1"
            rows_data = []
            for row in table.getElementsByType(TableRow):
                cells = []
                for cell in row.getElementsByType(TableCell):
                    cell_value = ""
                    for p in cell.getElementsByType(P):
                        cell_value += str(p)
                    # Check for 'value' attribute (numeric)
                    val_attr = cell.getAttribute('value')
                    if val_attr is not None and val_attr != '':
                        try:
                            cell_value = float(val_attr)
                        except ValueError:
                            pass
                    # Handle date
                    date_val = cell.getAttribute('date-value')
                    if date_val:
                        cell_value = date_val
                    cells.append(_normalize_value(cell_value))
                if cells:
                    rows_data.append(cells)

            if rows_data:
                max_cols = max(len(r) for r in rows_data)
                for r in rows_data:
                    while len(r) < max_cols:
                        r.append("")
                result[sheet_name] = (rows_data[0], rows_data[1:])
            else:
                result[sheet_name] = ([], [])
        return result
    finally:
        _safe_unlink(tmp_path)


# =====================================================================
# XLS Reader (via xlrd)
# =====================================================================
def read_xls(file_bytes: bytes) -> Dict[str, Tuple[List[str], List[List[str]]]]:
    """Returns {sheet_name: (headers, rows)} from .xls file."""
    try:
        import xlrd
    except ImportError:
        raise ValueError("xlrd не установлен. Установите: pip install xlrd")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xls")
    tmp_path = tmp.name
    try:
        tmp.write(file_bytes)
        tmp.flush()
        tmp.close()

        wb = xlrd.open_workbook(tmp_path)
        result = {}
        for sheet_name in wb.sheet_names():
            sheet = wb.sheet_by_name(sheet_name)
            rows_data = []
            for row_idx in range(sheet.nrows):
                row_data = [_normalize_value(sheet.cell_value(row_idx, col_idx)) for col_idx in range(sheet.ncols)]
                rows_data.append(row_data)
            if rows_data:
                result[sheet_name] = (rows_data[0], rows_data[1:])
            else:
                result[sheet_name] = ([], [])
        return result
    finally:
        _safe_unlink(tmp_path)


# =====================================================================
# Preview function for any supported format
# =====================================================================
def preview_file(
    file_bytes: bytes,
    filename: str,
    header_row_index: int = 0,
    preview_rows: int = 10,
) -> List[Dict[str, Any]]:
    fmt = detect_format(filename)
    result = []

    if fmt == 'csv':
        headers, data_rows = read_csv(file_bytes)
        if header_row_index >= 0 and header_row_index < len(data_rows):
            headers = data_rows[header_row_index]
            data_rows = data_rows[header_row_index + 1:]
        elif header_row_index >= len(data_rows):
            raise ValueError(f"header_row_index {header_row_index} превышает количество строк ({len(data_rows)})")
        elif header_row_index < 0:
            headers = _auto_generate_headers(len(headers) if headers else 0)
        result.append({
            "name": filename,
            "headers": headers,
            "sample_rows": data_rows[:preview_rows],
        })
        return result

    if fmt == 'tsv':
        headers, data_rows = read_csv(file_bytes, delimiter='\t')
        if header_row_index >= 0 and header_row_index < len(data_rows):
            headers = data_rows[header_row_index]
            data_rows = data_rows[header_row_index + 1:]
        elif header_row_index >= len(data_rows):
            raise ValueError(f"header_row_index {header_row_index} превышает количество строк ({len(data_rows)})")
        elif header_row_index < 0:
            headers = _auto_generate_headers(len(headers) if headers else 0)
        result.append({
            "name": filename,
            "headers": headers,
            "sample_rows": data_rows[:preview_rows],
        })
        return result

    if fmt == 'ods':
        sheets = read_ods(file_bytes)
        for sheet_name, (headers, data_rows) in sheets.items():
            if header_row_index >= 0 and header_row_index < len(data_rows):
                headers = data_rows[header_row_index]
                data_rows = data_rows[header_row_index + 1:]
            elif header_row_index >= len(data_rows):
                raise ValueError(f"header_row_index {header_row_index} превышает количество строк ({len(data_rows)})")
            elif header_row_index < 0:
                headers = _auto_generate_headers(len(headers) if headers else 0)
            result.append({
                "name": sheet_name,
                "headers": headers,
                "sample_rows": data_rows[:preview_rows],
            })
        return result

    if fmt == 'xls':
        sheets = read_xls(file_bytes)
        for sheet_name, (headers, data_rows) in sheets.items():
            if header_row_index >= 0 and header_row_index < len(data_rows):
                headers = data_rows[header_row_index]
                data_rows = data_rows[header_row_index + 1:]
            elif header_row_index >= len(data_rows):
                raise ValueError(f"header_row_index {header_row_index} превышает количество строк ({len(data_rows)})")
            elif header_row_index < 0:
                headers = _auto_generate_headers(len(headers) if headers else 0)
            result.append({
                "name": sheet_name,
                "headers": headers,
                "sample_rows": data_rows[:preview_rows],
            })
        return result

    raise ValueError(f"Неподдерживаемый формат файла: {filename}")


# =====================================================================
# Import function for any supported format
# =====================================================================
def import_file_as_datasets(
    db: Session,
    user_id: int,
    file_bytes: bytes,
    filename: str,
    sheet_names: Optional[List[str]] = None,
    header_row_index: int = 0,
    create_mode: str = "new",
    target_dataset_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    fmt = detect_format(filename)
    created_ids = []
    errors = []

    if fmt == 'csv':
        headers, data_rows = read_csv(file_bytes)
        if header_row_index >= 0 and header_row_index < len(data_rows):
            headers = data_rows[header_row_index]
            data_rows = data_rows[header_row_index + 1:]
        elif header_row_index >= len(data_rows):
            errors.append(f"header_row_index {header_row_index} превышает количество строк ({len(data_rows)})")
            return {"created_datasets": created_ids, "errors": errors, "total_sheets_processed": len(created_ids) + len(errors)}
        elif header_row_index < 0:
            headers = _auto_generate_headers(len(headers) if headers else 0)

        if not headers:
            errors.append("Не найдены заголовки в CSV")
        else:
            ds_name = os.path.splitext(os.path.basename(filename))[0]
            columns = _build_columns_from_headers(headers, data_rows[:100])
            _create_or_replace_dataset(db, user_id, ds_name, columns, data_rows, headers,
                                       create_mode, target_dataset_ids, 0, created_ids, errors)

    elif fmt == 'tsv':
        headers, data_rows = read_csv(file_bytes, delimiter='\t')
        if header_row_index >= 0 and header_row_index < len(data_rows):
            headers = data_rows[header_row_index]
            data_rows = data_rows[header_row_index + 1:]
        elif header_row_index >= len(data_rows):
            errors.append(f"header_row_index {header_row_index} превышает количество строк ({len(data_rows)})")
            return {"created_datasets": created_ids, "errors": errors, "total_sheets_processed": len(created_ids) + len(errors)}
        elif header_row_index < 0:
            headers = _auto_generate_headers(len(headers) if headers else 0)

        if not headers:
            errors.append("Не найдены заголовки в TSV")
        else:
            ds_name = os.path.splitext(os.path.basename(filename))[0]
            columns = _build_columns_from_headers(headers, data_rows[:100])
            _create_or_replace_dataset(db, user_id, ds_name, columns, data_rows, headers,
                                       create_mode, target_dataset_ids, 0, created_ids, errors)

    elif fmt == 'ods':
        sheets = read_ods(file_bytes)
        _process_sheets(db, user_id, sheets, sheet_names, header_row_index,
                        create_mode, target_dataset_ids, created_ids, errors, filename)

    elif fmt == 'xls':
        sheets = read_xls(file_bytes)
        _process_sheets(db, user_id, sheets, sheet_names, header_row_index,
                        create_mode, target_dataset_ids, created_ids, errors, filename)

    else:
        errors.append(f"Неподдерживаемый формат файла: {filename}")

    return {
        "created_datasets": created_ids,
        "errors": errors,
        "total_sheets_processed": len(created_ids) + len(errors),
    }


def _process_sheets(
    db: Session,
    user_id: int,
    sheets: Dict[str, Tuple[List[str], List[List[str]]]],
    sheet_names: Optional[List[str]],
    header_row_index: int,
    create_mode: str,
    target_dataset_ids: Optional[List[int]],
    created_ids: List[int],
    errors: List[str],
    filename: str,
):
    """Импортирует все листы ODS/XLS в один датасет как под-листы."""
    names_to_process = sheet_names or list(sheets.keys())
    processed_sheets = []
    merged_columns = []
    merged_col_ids = set()

    # First pass: collect and validate all sheets
    for sheet_name in names_to_process:
        if sheet_name not in sheets:
            errors.append(f"Лист '{sheet_name}' не найден")
            continue
        try:
            headers, data_rows = sheets[sheet_name]
            if header_row_index >= 0 and header_row_index < len(data_rows):
                headers = data_rows[header_row_index]
                data_rows = data_rows[header_row_index + 1:]
            elif header_row_index >= len(data_rows):
                raise ValueError(f"header_row_index {header_row_index} превышает количество строк ({len(data_rows)})")
            elif header_row_index < 0:
                headers = _auto_generate_headers(len(headers) if headers else 0)

            if not headers:
                errors.append(f"Лист '{sheet_name}': не найдено заголовков")
                continue

            columns = _build_columns_from_headers(headers, data_rows[:100])
            if len(processed_sheets) > 0:
                prefix = f"s{len(processed_sheets)}_"
                for col in columns:
                    col["id"] = prefix + col["id"]
            for col in columns:
                if col["id"] not in merged_col_ids:
                    merged_columns.append(col)
                    merged_col_ids.add(col["id"])

            sub_sheet_id = "main" if len(processed_sheets) == 0 else str(uuid.uuid4())
            processed_sheets.append({
                "sub_sheet_id": sub_sheet_id,
                "sheet_name": sheet_name,
                "headers": headers,
                "data_rows": data_rows,
                "columns": columns,
            })
        except Exception as e:
            errors.append(f"Лист '{sheet_name}': {str(e)}")

    if not processed_sheets:
        return

    if create_mode == "new":
        ds_name = os.path.splitext(os.path.basename(filename))[0]
        existing = db.query(models.Dataset).filter(
            models.Dataset.name == ds_name,
            models.Dataset.owner_id == user_id,
            models.Dataset.archived == False,
        ).count()
        name = ds_name if existing == 0 else f"{ds_name} ({existing + 1})"

        sub_sheets = [
            {"id": ps["sub_sheet_id"], "name": ps["sheet_name"], "order": i,
             "frozen_rows": 0, "frozen_columns": 0}
            for i, ps in enumerate(processed_sheets)
        ]

        dataset = models.Dataset(
            name=name,
            owner_id=user_id,
            columns=merged_columns,
            header_row_1=None,
            header_row_2=None,
            header_row_2_colors=None,
            archived=False,
            sub_sheets=sub_sheets,
        )
        db.add(dataset)
        db.flush()

        for ps in processed_sheets:
            sheet_id = ps["sub_sheet_id"]
            row_order = 0
            for data_row in ps["data_rows"]:
                data = {}
                for ci, col_def in enumerate(merged_columns):
                    val = data_row[ci] if ci < len(data_row) else ""
                    data[col_def["id"]] = val
                if not any(v for v in data.values() if v):
                    continue
                db_row = models.Row(
                    dataset_id=dataset.id,
                    sheet_id=sheet_id,
                    data=data,
                    formulas={},
                    cell_styles={},
                    row_order=row_order,
                    version=1,
                )
                db.add(db_row)
                row_order += 1

        db.commit()
        db.refresh(dataset)
        created_ids.append(dataset.id)

    elif create_mode == "replace":
        if not target_dataset_ids:
            raise ValueError("Для режима replace требуется target_dataset_id")
        dataset_id = target_dataset_ids[0]
        dataset = db.query(models.Dataset).filter(models.Dataset.id == dataset_id).first()
        if not dataset:
            raise ValueError(f"Датасет с ID {dataset_id} не найден")

        db.query(models.Row).filter(models.Row.dataset_id == dataset.id).delete()
        dataset.columns = merged_columns

        sub_sheets = [
            {"id": ps["sub_sheet_id"], "name": ps["sheet_name"], "order": i,
             "frozen_rows": 0, "frozen_columns": 0}
            for i, ps in enumerate(processed_sheets)
        ]
        dataset.sub_sheets = sub_sheets
        db.flush()

        for ps in processed_sheets:
            sheet_id = ps["sub_sheet_id"]
            row_order = 0
            for data_row in ps["data_rows"]:
                data = {}
                for ci, col_def in enumerate(merged_columns):
                    val = data_row[ci] if ci < len(data_row) else ""
                    data[col_def["id"]] = val
                if not any(v for v in data.values() if v):
                    continue
                db_row = models.Row(
                    dataset_id=dataset.id,
                    sheet_id=sheet_id,
                    data=data,
                    formulas={},
                    cell_styles={},
                    row_order=row_order,
                    version=1,
                )
                db.add(db_row)
                row_order += 1

        db.commit()
        db.refresh(dataset)
        created_ids.append(dataset.id)

# =====================================================================
# Single-sheet dataset helper (CSV, TSV)
# =====================================================================
def _create_or_replace_dataset(
    db: Session,
    user_id: int,
    ds_name: str,
    columns: List[Dict[str, Any]],
    data_rows: List[List[str]],
    headers: List[str],
    create_mode: str,
    target_dataset_ids: Optional[List[int]],
    idx: int,
    created_ids: List[int],
    errors: List[str],
):
    """������ ��� �������� ���� ������� ��� CSV/TSV (���� ����)."""
    try:
        if create_mode == "new":
            existing = db.query(models.Dataset).filter(
                models.Dataset.name == ds_name,
                models.Dataset.owner_id == user_id,
                models.Dataset.archived == False,
            ).count()
            name = ds_name
            if existing > 0:
                name = f"{ds_name} ({existing + 1})"
            dataset = models.Dataset(
                name=name,
                owner_id=user_id,
                columns=columns,
                header_row_1=None,
                header_row_2=None,
                header_row_2_colors=None,
                archived=False,
                sub_sheets=[{"id": "main", "name": ds_name, "order": 0,
                             "frozen_rows": 0, "frozen_columns": 0}],
            )
            db.add(dataset)
            db.flush()

            row_order = 0
            for data_row in data_rows:
                data = {}
                for ci, col_def in enumerate(columns):
                    val = data_row[ci] if ci < len(data_row) else ""
                    data[col_def["id"]] = val
                if not any(v for v in data.values() if v):
                    continue
                db_row = models.Row(
                    dataset_id=dataset.id,
                    sheet_id="main",
                    data=data,
                    formulas={},
                    cell_styles={},
                    row_order=row_order,
                    version=1,
                )
                db.add(db_row)
                row_order += 1

            db.commit()
            db.refresh(dataset)
            created_ids.append(dataset.id)

        elif create_mode == "replace":
            if not target_dataset_ids or idx >= len(target_dataset_ids):
                raise ValueError("������������ target_dataset_ids")
            dataset_id = target_dataset_ids[idx]
            dataset = db.query(models.Dataset).filter(models.Dataset.id == dataset_id).first()
            if not dataset:
                raise ValueError(f"������� � ID {dataset_id} �� ������")

            db.query(models.Row).filter(models.Row.dataset_id == dataset.id).delete()
            dataset.columns = columns
            if not dataset.sub_sheets:
                dataset.sub_sheets = [{"id": "main", "name": ds_name, "order": 0,
                                       "frozen_rows": 0, "frozen_columns": 0}]
            db.flush()

            row_order = 0
            for data_row in data_rows:
                data = {}
                for ci, col_def in enumerate(columns):
                    val = data_row[ci] if ci < len(data_row) else ""
                    data[col_def["id"]] = val
                if not any(v for v in data.values() if v):
                    continue
                db_row = models.Row(
                    dataset_id=dataset.id,
                    sheet_id="main",
                    data=data,
                    formulas={},
                    cell_styles={},
                    row_order=row_order,
                    version=1,
                )
                db.add(db_row)
                row_order += 1

            db.commit()
            db.refresh(dataset)
            created_ids.append(dataset.id)

    except Exception as e:
        db.rollback()
        raise e
