# backend/app/services/excel_export_service.py

import io
import re
import xlsxwriter
from sqlalchemy.orm import Session
from app import models
import structlog

logger = structlog.get_logger()

MAX_SHEET_NAME_LENGTH = 31


def _make_format(workbook, styles: dict = None) -> object:
    """Create an xlsxwriter format from cell style dict."""
    fmt = {}
    if not styles:
        return workbook.add_format(fmt)

    if styles.get("bold"):
        fmt["bold"] = True
    if styles.get("italic"):
        fmt["italic"] = True
    if styles.get("underline"):
        fmt["underline"] = True
    if styles.get("strikethrough"):
        fmt["strikethrough"] = True
    if styles.get("textDecoration") == "line-through":
        fmt["strikethrough"] = True
    if styles.get("fontFamily"):
        fmt["font_name"] = styles["fontFamily"]
    if styles.get("fontSize"):
        size = re.sub(r"[^\d.]", "", str(styles["fontSize"]))
        if size:
            fmt["font_size"] = int(float(size))
    if styles.get("color"):
        fmt["font_color"] = styles["color"]
    if styles.get("backgroundColor"):
        fmt["bg_color"] = styles["backgroundColor"]
    if styles.get("textAlign"):
        fmt["align"] = styles["textAlign"]
    if styles.get("verticalAlign"):
        fmt["valign"] = styles["verticalAlign"]
    if styles.get("whiteSpace") == "wrap" or styles.get("wrapText"):
        fmt["text_wrap"] = True

    # Borders — xlsxwriter uses lowercase keys 'top', 'bottom', 'left', 'right'
    _BORDER_CSS_MAP = {
        "solid": 1, "thin": 1,
        "medium": 2,
        "dashed": 3,
        "dotted": 4,
        "thick": 5,
        "double": 6,
        "hair": 7,
    }
    _BORDER_RE = re.compile(r"^(?:\d+px\s+)?(\w+)(?:\s+(#[0-9a-fA-F]{3,8}|rgb[a]?\([^)]*\)|[a-z]+))?$")
    for side in ("top", "bottom", "left", "right"):
        key = f"border{side.capitalize()}"
        val = styles.get(key)
        if val and val != "none":
            m = _BORDER_RE.match(val)
            if m:
                style_word = m.group(1).lower()
                color = m.group(2)
                xw_style = _BORDER_CSS_MAP.get(style_word, 1)
                fmt[side] = xw_style
                if color:
                    fmt[f"{side}_color"] = color

    return workbook.add_format(fmt)


def _make_number_format(workbook, nf: str):
    """Create format for number formatting string."""
    xlsx_map = {
        "number": "#,##0.00",
        "percent": "0.00%",
        "financial": '#,##0.00" ₽"',
        "currency": '#,##0.00" ₽"',
        "date": "DD.MM.YYYY",
        "time": "HH:MM:SS",
    }
    return workbook.add_format({"num_format": xlsx_map.get(nf, nf)})


def _col_letter(idx: int) -> str:
    """Convert 0-based column index to Excel column letter (A, B, ..., Z, AA...)."""
    letter = ""
    while idx >= 0:
        letter = chr(65 + idx % 26) + letter
        idx = idx // 26 - 1
    return letter


def _univer_to_css_style(style: dict) -> dict:
    """Convert Univer cell style format to CSS-like format expected by _make_format."""
    if not isinstance(style, dict):
        return {}
    result = {}
    if style.get("bl"):
        result["bold"] = True
    if style.get("it"):
        result["italic"] = True
    if style.get("ff"):
        result["fontFamily"] = style["ff"]
    if style.get("fs"):
        result["fontSize"] = str(style["fs"])
    clr = style.get("cl")
    if isinstance(clr, dict):
        result["color"] = clr.get("rgb", "")
    elif isinstance(clr, str):
        result["color"] = clr
    bg = style.get("bg")
    if isinstance(bg, dict):
        result["backgroundColor"] = bg.get("rgb", "")
    elif isinstance(bg, str):
        result["backgroundColor"] = bg
    ht = style.get("ht")
    if ht is not None:
        result["textAlign"] = {0: "left", 1: "center", 2: "right", 3: "fill"}.get(ht, "left")
    vt = style.get("vt")
    if vt is not None:
        result["verticalAlign"] = {0: "top", 1: "middle", 2: "bottom"}.get(vt, "bottom")
    if style.get("tb"):
        result["wrapText"] = True
    td = style.get("td")
    if isinstance(td, dict) and td.get("s") == 1:
        result["strikethrough"] = True
    ul = style.get("ul")
    if isinstance(ul, dict) and ul.get("s"):
        result["underline"] = True
    bd = style.get("bd")
    if isinstance(bd, dict):
        border_style_map = {1: "thin", 2: "medium", 3: "dashed", 4: "dotted", 5: "thick", 6: "double", 7: "hair"}
        side_map = {"l": "Left", "r": "Right", "t": "Top", "b": "Bottom"}
        for uk, side in side_map.items():
            b = bd.get(uk)
            if isinstance(b, dict) and b.get("s"):
                bs = border_style_map.get(b["s"], "thin")
                bc = b.get("cl")
                color = bc.get("rgb", "") if isinstance(bc, dict) else ""
                result[f"border{side}"] = bs + (f" {color}" if color else "")
    return result


def export_dataset_to_excel(db: Session, dataset_id: int) -> bytes:
    """
    Экспортирует датасет в формат Excel (.xlsx).
    Включает: заголовки колонок, header_row_1/2, стили, форматы чисел,
    выпадающие списки, данные, формулы.
    """
    dataset = db.query(models.Dataset).filter(models.Dataset.id == dataset_id).first()
    if not dataset:
        raise ValueError("Датасет не найден")

    rows = (
        db.query(models.Row)
        .filter(models.Row.dataset_id == dataset_id)
        .order_by(models.Row.row_order)
        .all()
    )

    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})

    sheet_name = dataset.name[:MAX_SHEET_NAME_LENGTH]
    worksheet = workbook.add_worksheet(sheet_name)

    columns = dataset.columns or []
    col_ids = [c["id"] for c in columns]

    # Track current row
    r = 0

    # ---- header_row_1 (итоги) ----
    hr1 = dataset.header_row_1 or {}
    if hr1:
        for ci, col_def in enumerate(columns):
            val = hr1.get(col_def["id"], "")
            if val:
                worksheet.write(r, ci, val)
        r += 1

    # ---- header_row_2 (группы) ----
    hr2 = dataset.header_row_2 or {}
    if hr2:
        for ci, col_def in enumerate(columns):
            val = hr2.get(col_def["id"], "")
            if val:
                f = workbook.add_format({"bold": True, "bg_color": "#f0f0f0"})
                worksheet.write(r, ci, val, f)
        r += 1

    # ---- Заголовки колонок ----
    header_fmt = workbook.add_format({"bold": True, "bg_color": "#d9e1f2", "border": 1})
    for ci, col_def in enumerate(columns):
        header = col_def.get("header") or _col_letter(ci)
        worksheet.write(r, ci, header, header_fmt)
    r += 1

    # ---- Данные ----
    style_map = dataset.styles or {}
    for row in rows:
        cell_styles = row.cell_styles or {}
        for ci, col_def in enumerate(columns):
            col_id = col_def["id"]
            raw_style = cell_styles.get(col_id, {})
            if isinstance(raw_style, str):
                raw_style = style_map.get(raw_style, {})
            css_style = _univer_to_css_style(raw_style)
            fmt = _make_format(workbook, css_style)

            # Number format
            nf = (row.data or {}).get("_numberFormats", {}).get(col_id)
            if nf and nf != "auto":
                fmt = _make_number_format(workbook, nf)

            formula = (row.formulas or {}).get(col_id)
            if formula and isinstance(formula, str) and formula.startswith("="):
                worksheet.write_formula(r, ci, formula, fmt)
            else:
                value = (row.data or {}).get(col_id, "")
                if value is None:
                    value = ""
                worksheet.write(r, ci, value, fmt)

        r += 1

    # ---- Data validation (выпадающие списки) ----
    data_start = r - len(rows) if rows else r
    for ci, col_def in enumerate(columns):
        validation = col_def.get("validation")
        if validation and validation.get("type") == "list":
            items = validation.get("items") or []
            if items:
                source = ",".join(items)
                # xlsxwriter лимит 255 символов для inline-списка
                if len(source) > 255:
                    hidden_sheet = workbook.add_worksheet("_dv_" + _col_letter(ci))
                    hidden_sheet.hide()
                    for idx, item in enumerate(items):
                        hidden_sheet.write(idx, 0, item)
                    source = f"_dv_{_col_letter(ci)}!$A$1:$A${len(items)}"
                worksheet.data_validation(data_start, ci, r - 1, ci, {
                    "validate": "list",
                    "source": source,
                    "input_title": "Выберите значение",
                    "input_message": validation.get("help_text", ""),
                    "error_title": "Недопустимое значение",
                    "error_message": "Выберите значение из списка",
                })

    # ---- Column widths ----
    worksheet.set_column(0, len(col_ids) - 1, 18)

    workbook.close()
    output.seek(0)
    return output.getvalue()