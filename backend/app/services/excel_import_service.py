# backend/app/services/excel_import_service.py

import tempfile
import os
import uuid
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

import structlog
from python_calamine import CalamineWorkbook
from sqlalchemy import insert

from app import models
from app.services.russian_formulas import convert_russian_formula
from sqlalchemy.orm import Session

logger = structlog.get_logger()


# =============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =============================================================================

def _open_workbook(file_bytes: bytes) -> tuple:
    """
    Открывает CalamineWorkbook из байт через временный файл.
    Возвращает (workbook, tmp_path) — tmp_path нужно удалить после использования.
    """
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    tmp_path = tmp.name
    try:
        tmp.write(file_bytes)
        tmp.flush()
        tmp.close()
        wb = CalamineWorkbook.from_path(tmp_path)
        return wb, tmp_path
    except Exception as e:
        _safe_unlink(tmp_path)
        raise ValueError(f"Не удалось прочитать Excel-файл: {str(e)}")


def _safe_unlink(path: str):
    try:
        os.unlink(path)
    except Exception:
        pass


def _col_letter_to_index(col_letter: str) -> int:
    """Преобразует букву колонки Excel ('A', 'B', ..., 'AA', ...) в 0-индекс."""
    idx = 0
    for ch in col_letter.upper():
        idx = idx * 26 + (ord(ch) - ord('A') + 1)
    return idx - 1


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


def guess_column_type(values: List[Optional[str]]) -> str:
    non_empty = [v for v in values if v is not None and str(v).strip() != ""]
    if not non_empty:
        return "string"
    if all(_is_number(str(v)) for v in non_empty):
        return "number"
    if all(_is_date(str(v)) for v in non_empty):
        return "date"
    return "string"


def _build_columns_from_headers(headers: List[str], sample_data: List[List[Optional[str]]]) -> List[Dict[str, Any]]:
    import string

    def excel_style(col_idx: int) -> str:
        result = ""
        col_idx += 1
        while col_idx > 0:
            col_idx, remainder = divmod(col_idx - 1, 26)
            result = string.ascii_uppercase[remainder] + result
        return result

    columns = []
    num_samples = min(len(sample_data), 100)
    sample_columns = []
    for col_idx in range(len(headers)):
        col_vals = []
        for row in sample_data[:num_samples]:
            if col_idx < len(row):
                val = row[col_idx]
                if isinstance(val, datetime):
                    col_vals.append(val.strftime("%Y-%m-%d"))
                elif val is None:
                    col_vals.append(None)
                else:
                    col_vals.append(str(val))
            else:
                col_vals.append(None)
        sample_columns.append(col_vals)

    for col_idx, header in enumerate(headers):
        col_type = guess_column_type(sample_columns[col_idx]) if col_idx < len(sample_columns) else "string"
        col_id = excel_style(col_idx)
        columns.append({
            "id": col_id,
            "header": str(header).strip() if header else col_id,
            "type": col_type,
            "editableBy": [],
            "colorGroup": None,
        })
    return columns


def _auto_generate_headers(max_cols: int) -> List[str]:
    """Генерирует заголовки A, B, C... (без headers из файла)."""
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


def _get_sheet_data_and_formulas(sheet, max_rows: Optional[int] = None) -> Tuple[List[List[Any]], List[Dict[int, str]]]:
    """
    Читает лист Excel через iter_rows().
    Возвращает (all_values, all_formulas_maps):
    - all_values: список строк со значениями
    - all_formulas_maps: список словарей {col_index: formula_string}
      (из Calamine, если версия возвращает CalamineCell с формулами)
    """
    all_values = []
    all_formulas_maps = []
    for cell_row in sheet.iter_rows():
        if max_rows is not None and len(all_values) >= max_rows:
            break
        values = []
        formulas_map = {}
        for col_idx, cell in enumerate(cell_row):
            if hasattr(cell, 'value'):
                # CalamineCell (новые версии python-calamine)
                values.append(cell.value)
                formula_str = None
                if hasattr(cell, 'is_formula') and cell.is_formula:
                    if hasattr(cell, 'formula'):
                        formula_str = cell.formula
                    if not formula_str and hasattr(cell, 'inner_value'):
                        formula_str = str(cell.inner_value) if cell.inner_value else None
                if formula_str:
                    formulas_map[col_idx] = formula_str
            else:
                # Сырое значение (python-calamine 0.6.2) — без информации о формулах
                values.append(cell)
        all_values.append(values)
        all_formulas_maps.append(formulas_map)

    if all_values:
        max_cols = max(len(r) for r in all_values)
        for ri in range(len(all_values)):
            while len(all_values[ri]) < max_cols:
                all_values[ri].append(None)
    return all_values, all_formulas_maps


_EXCEL_ERRORS = frozenset({"#VALUE!", "#REF!", "#DIV/0!", "#NAME?", "#N/A", "#NUM!", "#NULL!"})


def _is_excel_error(val) -> bool:
    return isinstance(val, str) and val in _EXCEL_ERRORS


def _normalize_value(val):
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, (int, float)):
        return val
    if val is None:
        return ""
    if _is_excel_error(val):
        return ""
    return str(val)


def _parse_row_with_formulas(row, columns_def, formulas_map: Dict[int, str] = None):
    """
    Парсит строку данных, учитывая карту формул {col_index: formula_string}.
    Если formulas_map задан и содержит колонку, формула берётся оттуда,
    иначе проверяется, не начинается ли значение с '='.
    Сохраняет кешированное значение (cached value) для ячеек с формулами,
    чтобы после импорта ячейки не были пустыми.
    Для ячеек с формулой, у которых кешированное значение — ошибка Excel
    (#VALUE! и т.п.), сохраняется пустая строка, чтобы Univer пересчитал
    формулу заново.
    """
    data = {}
    formulas = {}
    for col_idx, col_def in enumerate(columns_def):
        col_id = col_def["id"]
        if col_idx < len(row):
            cell_val = row[col_idx]
            if formulas_map and col_idx in formulas_map:
                formula_str = formulas_map[col_idx]
                if not formula_str.startswith("="):
                    formula_str = "=" + formula_str
                formulas[col_id] = convert_russian_formula(formula_str)
                data[col_id] = "" if _is_excel_error(cell_val) else _normalize_value(cell_val)
            elif isinstance(cell_val, str) and cell_val.startswith("="):
                formulas[col_id] = convert_russian_formula(cell_val)
                data[col_id] = "" if _is_excel_error(cell_val) else _normalize_value(cell_val)
            else:
                data[col_id] = _normalize_value(cell_val)
        else:
            data[col_id] = ""
    return data, formulas


def _raw_color_to_hex(color_elem, theme_colors: Optional[Dict[int, str]] = None) -> Optional[str]:
    """Парсит openpyxl Color из raw XML элемента в hex (#RRGGBB)."""
    if color_elem is None:
        return None
    try:
        rgb = color_elem.get('rgb')
        if rgb:
            rgb_str = str(rgb).upper().replace('#', '')
            if len(rgb_str) == 8:
                if rgb_str.startswith('00') and rgb_str[2:] == '000000':
                    return None
                return '#' + rgb_str[2:]
            if len(rgb_str) == 6:
                return '#' + rgb_str
            return None

        theme = color_elem.get('theme')
        if theme is not None:
            if theme_colors is None:
                theme_colors = {
                    0: '#FFFFFF', 1: '#000000', 2: '#EEEEEE', 3: '#44546A',
                    4: '#4472C4', 5: '#ED7D31', 6: '#A5A5A5', 7: '#FFCD00',
                    8: '#70AD47', 9: '#5B9BD5', 10: '#0563C1', 11: '#954F72',
                }
            hex_color = theme_colors.get(int(theme))
            if hex_color is None:
                return None
            tint = color_elem.get('tint')
            if tint:
                hex_color = _apply_tint(hex_color, float(tint))
            return hex_color

        indexed = color_elem.get('indexed')
        if indexed is not None:
            return _indexed_color_to_hex(int(indexed))

        auto = color_elem.get('auto')
        if auto == '1':
            return None

        return None
    except Exception:
        return None


def _parse_theme_colors_from_zip(zf) -> Dict[int, str]:
    """Парсит 12 цветов темы из xl/theme/theme1.xml.

    Порядок в OOXML: dk1(1), lt1(0), dk2(3), lt2(2),
    accent1(4)…accent6(9), hlink(10), folHlink(11).
    """
    import xml.etree.ElementTree as ET
    THEME_NS = 'http://schemas.openxmlformats.org/drawingml/2006/main'
    TAG_TO_INDEX = {
        'dk1': 1, 'lt1': 0, 'dk2': 3, 'lt2': 2,
        'accent1': 4, 'accent2': 5, 'accent3': 6, 'accent4': 7,
        'accent5': 8, 'accent6': 9, 'hlink': 10, 'folHlink': 11,
    }
    colors = {
        0: '#FFFFFF', 1: '#000000', 2: '#EEEEEE', 3: '#44546A',
        4: '#4472C4', 5: '#ED7D31', 6: '#A5A5A5', 7: '#FFCD00',
        8: '#70AD47', 9: '#5B9BD5', 10: '#0563C1', 11: '#954F72',
    }
    try:
        tree = ET.parse(zf.open('xl/theme/theme1.xml'))
        root = tree.getroot()
        for elem in root.iter(f'{{{THEME_NS}}}clrScheme'):
            for child in elem:
                tag = child.tag.split('}')[-1]
                if tag in TAG_TO_INDEX:
                    idx = TAG_TO_INDEX[tag]
                    for c in child:
                        ctag = c.tag.split('}')[-1]
                        if ctag == 'srgbClr':
                            colors[idx] = '#' + c.get('val', '').upper()
                        elif ctag == 'sysClr':
                            last = c.get('lastClr')
                            if last:
                                colors[idx] = '#' + last.upper()
            break
    except Exception:
        pass
    return colors


def _parse_alignment(align_elem) -> Dict[str, str]:
    """Парсит alignment XML элемент в стилевой dict."""
    style = {}
    horizontal = align_elem.get('horizontal')
    if horizontal:
        style['textAlign'] = horizontal
    vertical = align_elem.get('vertical')
    if vertical:
        style['verticalAlign'] = vertical
    wrap = align_elem.get('wrapText')
    if wrap == '1':
        style['whiteSpace'] = 'normal'
    return style


def _apply_tint(hex_color: str, tint: float) -> str:
    """Применяет tint (осветление/затемнение) к hex-цвету."""
    try:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        if tint > 0:
            r = int(r + (255 - r) * tint)
            g = int(g + (255 - g) * tint)
            b = int(b + (255 - b) * tint)
        elif tint < 0:
            tint = abs(tint)
            r = int(r * (1 - tint))
            g = int(g * (1 - tint))
            b = int(b * (1 - tint))
        return f'#{r:02x}{g:02x}{b:02x}'
    except Exception:
        return hex_color


def _indexed_color_to_hex(index) -> Optional[str]:
    """Конвертирует indexed-цвет openpyxl в hex."""
    if index is None or index < 0:
        return None
    palette = [
        '#000000', '#FFFFFF', '#FF0000', '#00FF00', '#0000FF', '#FFFF00',
        '#FF00FF', '#00FFFF', '#000000', '#FFFFFF', '#FF0000', '#00FF00',
        '#0000FF', '#FFFF00', '#FF00FF', '#00FFFF', '#800000', '#008000',
        '#000080', '#808000', '#800080', '#008080', '#C0C0C0', '#808080',
        '#9999FF', '#993366', '#FFFFCC', '#CCFFFF', '#660066', '#FF8080',
        '#0066CC', '#CCCCFF', '#000080', '#FF00FF', '#FFFF00', '#00FFFF',
        '#800080', '#800000', '#008080', '#0000FF', '#666699', '#808080',
        '#003366', '#333399', '#333333', '#666666', '#999999', '#CCCCCC',
    ]
    if index < len(palette):
        return palette[index]
    return '#000000'


def _extract_styles_and_metadata(file_bytes: bytes
) -> Tuple[Dict[str, Dict[int, Dict[str, Dict[str, Any]]]], Dict[str, Dict[str, Any]]]:
    """Извлекает стили и метаданные (merged_cells, column_widths, row_heights, формулы)
    из xlsx через zip + XML за один проход по каждому листу."""
    import zipfile
    import xml.etree.ElementTree as ET
    import io

    NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'

    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes), 'r') as z:
            theme_colors = _parse_theme_colors_from_zip(z)

            wb_tree = ET.parse(z.open('xl/workbook.xml'))
            wb_root = wb_tree.getroot()
            sheet_list = []
            for sheet_elem in wb_root.iter(f'{{{NS}}}sheet'):
                name = sheet_elem.get('name')
                r_id = sheet_elem.get(
                    '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
                )
                if name and r_id:
                    sheet_list.append((name, r_id))

            try:
                rels_tree = ET.parse(z.open('xl/_rels/workbook.xml.rels'))
            except KeyError:
                rels_tree = ET.parse(z.open('xl/workbook.xml.rels'))
            rels_root = rels_tree.getroot()
            REL_NS = 'http://schemas.openxmlformats.org/package/2006/relationships'
            rId_to_path = {}
            for rel_elem in rels_root.iter(f'{{{REL_NS}}}Relationship'):
                rel_id = rel_elem.get('Id')
                target = rel_elem.get('Target')
                if rel_id and target:
                    rId_to_path[rel_id] = target.lstrip('/')

            fonts = []
            fills = []
            borders = []
            cell_xfs = []
            cell_style_xfs = []

            try:
                style_tree = ET.parse(z.open('xl/styles.xml'))
                style_root = style_tree.getroot()
            except KeyError:
                style_root = None

            if style_root is not None:
                fonts_elem = style_root.find(f'{{{NS}}}fonts')
                if fonts_elem is not None:
                    for font_elem in fonts_elem:
                        font = {}
                        if font_elem.find(f'{{{NS}}}b') is not None:
                            font['bold'] = True
                        if font_elem.find(f'{{{NS}}}i') is not None:
                            font['italic'] = True
                        if font_elem.find(f'{{{NS}}}strike') is not None:
                            font['strikethrough'] = True
                        if font_elem.find(f'{{{NS}}}u') is not None:
                            font['underline'] = True
                        sz_elem = font_elem.find(f'{{{NS}}}sz')
                        if sz_elem is not None:
                            font['fontSize'] = float(sz_elem.get('val', 11))
                        name_elem = font_elem.find(f'{{{NS}}}name')
                        if name_elem is not None:
                            font['fontFamily'] = name_elem.get('val')
                        color_elem = font_elem.find(f'{{{NS}}}color')
                        if color_elem is not None:
                            ch = _raw_color_to_hex(color_elem, theme_colors)
                            if ch:
                                font['color'] = ch
                        fonts.append(font)

                fills_elem = style_root.find(f'{{{NS}}}fills')
                if fills_elem is not None:
                    for fill_elem in fills_elem:
                        fill = {}
                        pf = fill_elem.find(f'{{{NS}}}patternFill')
                        if pf is not None:
                            fg = pf.find(f'{{{NS}}}fgColor')
                            if fg is not None:
                                ch = _raw_color_to_hex(fg, theme_colors)
                                if ch:
                                    fill['backgroundColor'] = ch
                        fills.append(fill)

                borders_elem = style_root.find(f'{{{NS}}}borders')
                if borders_elem is not None:
                    for border_elem in borders_elem:
                        border = {}
                        for side_name, key_name in [
                            ('left', 'borderLeft'), ('right', 'borderRight'),
                            ('top', 'borderTop'), ('bottom', 'borderBottom'),
                        ]:
                            side = border_elem.find(f'{{{NS}}}{side_name}')
                            if side is not None:
                                side_style = side.get('style')
                                if side_style and side_style != 'none':
                                    color_elem = side.find(f'{{{NS}}}color')
                                    ch = _raw_color_to_hex(color_elem, theme_colors) if color_elem is not None else None
                                    cs = f' #{ch}' if ch else ''
                                    border[key_name] = f'{side_style} solid{cs}'
                        borders.append(border)

                csxf_elem = style_root.find(f'{{{NS}}}cellStyleXfs')
                if csxf_elem is not None:
                    cell_style_xfs = list(csxf_elem)

                cxf_elem = style_root.find(f'{{{NS}}}cellXfs')
                if cxf_elem is not None:
                    cell_xfs = list(cxf_elem)

            def resolve_xf(xf_elem):
                if xf_elem is None:
                    return {}
                style = {}
                xf_id = int(xf_elem.get('xfId', 0))
                base = cell_style_xfs[xf_id] if cell_style_xfs and xf_id < len(cell_style_xfs) else None

                if xf_elem.get('applyFont', '1') == '1':
                    f_id = int(xf_elem.get('fontId', 0))
                elif base is not None:
                    f_id = int(base.get('fontId', 0))
                else:
                    f_id = 0
                if f_id < len(fonts):
                    style.update(fonts[f_id])

                if xf_elem.get('applyFill', '1') == '1':
                    fl_id = int(xf_elem.get('fillId', 0))
                elif base is not None:
                    fl_id = int(base.get('fillId', 0))
                else:
                    fl_id = 0
                if fl_id < len(fills):
                    style.update(fills[fl_id])

                if xf_elem.get('applyBorder', '1') == '1':
                    b_id = int(xf_elem.get('borderId', 0))
                elif base is not None:
                    b_id = int(base.get('borderId', 0))
                else:
                    b_id = 0
                if b_id < len(borders):
                    style.update(borders[b_id])

                align_elem = xf_elem.find(f'{{{NS}}}alignment')
                if align_elem is not None:
                    style.update(_parse_alignment(align_elem))

                return style

            all_styles = {}
            all_metadata = {}

            for sheet_name, r_id in sheet_list:
                sheet_path = rId_to_path.get(r_id)
                if sheet_path is None:
                    continue
                if not sheet_path.startswith('xl/'):
                    sheet_path = 'xl/' + sheet_path

                sheet_styles = {}
                merged_cells = []
                column_widths = {}
                row_heights = {}
                formulas: Dict[int, Dict[str, str]] = {}

                try:
                    for event, elem in ET.iterparse(z.open(sheet_path), events=('end',)):
                        if elem.tag == f'{{{NS}}}row':
                            row_r = elem.get('r')
                            if row_r is None:
                                elem.clear()
                                continue
                            row_idx = int(row_r) - 1
                            ht = elem.get('ht')
                            if ht:
                                row_heights[row_idx] = float(ht)
                            row_style_dict = {}
                            row_formulas: Dict[str, str] = {}
                            for cell in elem:
                                cell_r = cell.get('r')
                                if cell_r is None:
                                    continue
                                col_id = ''.join(ch for ch in cell_r if ch.isalpha())
                                s = cell.get('s')
                                xf_idx = int(s) if s is not None else 0
                                if xf_idx < len(cell_xfs):
                                    style = resolve_xf(cell_xfs[xf_idx])
                                    if style:
                                        row_style_dict[col_id] = style
                                f_elem = cell.find(f'{{{NS}}}f')
                                if f_elem is not None and f_elem.text:
                                    formula = f_elem.text.strip()
                                    if not formula.startswith('='):
                                        formula = '=' + formula
                                    row_formulas[col_id] = formula
                            if row_style_dict:
                                sheet_styles[row_idx] = row_style_dict
                            if row_formulas:
                                formulas[row_idx] = row_formulas
                            elem.clear()

                        elif elem.tag == f'{{{NS}}}mergeCells':
                            for mc in elem:
                                ref = mc.get('ref', '')
                                if ref:
                                    parts = ref.split(':')
                                    if len(parts) == 2:
                                        sc = ''.join(ch for ch in parts[0] if ch.isalpha())
                                        sr = int(''.join(ch for ch in parts[0] if ch.isdigit())) - 1
                                        ec = ''.join(ch for ch in parts[1] if ch.isalpha())
                                        er = int(''.join(ch for ch in parts[1] if ch.isdigit())) - 1
                                        merged_cells.append({
                                            "startRow": sr,
                                            "endRow": er + 1,
                                            "startColumn": _col_letter_to_index(sc),
                                            "endColumn": _col_letter_to_index(ec) + 1,
                                        })
                            elem.clear()

                        elif elem.tag == f'{{{NS}}}cols':
                            for col_elem in elem:
                                min_c = int(col_elem.get('min', 1))
                                max_c = int(col_elem.get('max', 1))
                                width = col_elem.get('width')
                                if width:
                                    w = float(width)
                                    for ci in range(min_c, max_c + 1):
                                        column_widths[ci - 1] = w
                            elem.clear()
                except KeyError:
                    pass

                all_styles[sheet_name] = sheet_styles
                meta: Dict[str, Any] = {}
                if merged_cells:
                    meta["merged_cells"] = merged_cells
                if column_widths:
                    meta["column_widths"] = column_widths
                if row_heights:
                    meta["row_heights"] = row_heights
                if formulas:
                    meta["formulas"] = formulas
                all_metadata[sheet_name] = meta

            return all_styles, all_metadata
    except Exception as e:
        logger.warning("Не удалось извлечь стили и метаданные через zip/XML", error=str(e))
        return {}, {}


# =============================================================================
# КОНВЕРТАЦИЯ СТИЛЕЙ В Univer IStyleData
# =============================================================================

_BORDER_STYLE_MAP = {
    'none': 0,
    'thin': 1,
    'hair': 2,
    'dotted': 3,
    'dashed': 4,
    'dashDot': 5,
    'dashDotDot': 6,
    'double': 7,
    'medium': 8,
    'mediumDashed': 9,
    'mediumDashDot': 10,
    'mediumDashDotDot': 11,
    'slantDashDot': 12,
    'thick': 13,
}

_HORIZONTAL_ALIGN_MAP = {
    'left': 1,
    'center': 2,
    'right': 3,
    'justified': 4,
    'distributed': 6,
}

_VERTICAL_ALIGN_MAP = {
    'top': 1,
    'middle': 2,
    'bottom': 3,
}

_WRAP_STRATEGY_MAP = {
    'normal': 3,
    'clip': 2,
    'overflow': 1,
}


def _parse_border_style(border_str: str) -> Optional[Dict[str, Any]]:
    """Парсит строку типа 'thin solid #000000' в Univer IBorderStyleData."""
    if not border_str or not isinstance(border_str, str):
        return None
    parts = border_str.split()
    if len(parts) < 2:
        return None
    line_style = parts[0].lower()
    s = _BORDER_STYLE_MAP.get(line_style)
    if s is None or s == 0:
        return None
    color = None
    for p in parts[1:]:
        p = p.strip()
        if p.startswith('#'):
            color = p
            break
    result: Dict[str, Any] = {"s": s}
    if color:
        result["cl"] = {"rgb": color}
    return result if result.get("s", 0) != 0 else None


def _convert_style_to_univer(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Конвертирует raw style dict из Excel в Univer IStyleData."""
    result: Dict[str, Any] = {}

    if 'backgroundColor' in raw:
        bg = raw['backgroundColor']
        if bg and isinstance(bg, str):
            result['bg'] = {"rgb": bg}

    if 'color' in raw:
        cl = raw['color']
        if cl and isinstance(cl, str):
            result['cl'] = {"rgb": cl}

    for side, key in [('l', 'borderLeft'), ('r', 'borderRight'),
                      ('t', 'borderTop'), ('b', 'borderBottom')]:
        bval = raw.get(key)
        parsed = _parse_border_style(bval)
        if parsed:
            if 'bd' not in result:
                result['bd'] = {}
            result['bd'][side] = parsed

    if raw.get('bold'):
        result['bl'] = 1
    if raw.get('italic'):
        result['it'] = 1
    if 'fontSize' in raw:
        result['fs'] = raw['fontSize']
    if 'fontFamily' in raw:
        result['ff'] = raw['fontFamily']
    if raw.get('underline'):
        result['ul'] = {"s": 1}

    align = raw.get('textAlign', '').lower()
    if align in _HORIZONTAL_ALIGN_MAP:
        result['ht'] = _HORIZONTAL_ALIGN_MAP[align]

    valign = raw.get('verticalAlign', '').lower()
    if valign in _VERTICAL_ALIGN_MAP:
        result['vt'] = _VERTICAL_ALIGN_MAP[valign]

    ws = raw.get('whiteSpace', '').lower()
    if ws in _WRAP_STRATEGY_MAP:
        result['tb'] = _WRAP_STRATEGY_MAP[ws]

    return result


def _build_style_map(
    sheet_styles: Dict[int, Dict[str, Dict[str, Any]]]
) -> Tuple[Dict[str, Dict[str, Any]], Dict[int, Dict[str, str]]]:
    """Преобразует per-cell стили (полные dict-ы) в мапу с Univer-форматом и ключами.

    Возвращает:
    - style_map: { "s0": {Univer-IStyleData}, "s1": {...}, ... } — для Dataset.styles
    - cell_keys: { row_idx: { col_id: "s0" }, ... } — для Row.cell_styles
    """
    import json
    seen: Dict[str, str] = {}
    cell_keys: Dict[int, Dict[str, str]] = {}
    style_keys: Dict[str, Dict[str, Any]] = {}
    next_idx = 0

    for row_idx, row_cells in sheet_styles.items():
        row_out: Dict[str, str] = {}
        for col_id, raw_style in row_cells.items():
            univer_style = _convert_style_to_univer(raw_style)
            if not univer_style:
                continue
            canonical = json.dumps(univer_style, sort_keys=True)
            if canonical not in seen:
                key = f"s{next_idx}"
                next_idx += 1
                seen[canonical] = key
                style_keys[key] = univer_style
            row_out[col_id] = seen[canonical]
        if row_out:
            cell_keys[row_idx] = row_out

    return style_keys, cell_keys





# =============================================================================
# ПРЕДПРОСМОТР
# =============================================================================

def _format_preview_value(cell_val, formula_str=None):
    """Форматирует значение для предпросмотра, показывая формулу если есть."""
    if formula_str:
        return f"={formula_str.lstrip('=')}"
    return _normalize_value(cell_val) if cell_val is not None else ""


def preview_excel_sheets(file_bytes: bytes, preview_rows: int = 10, header_row_index: int = 0) -> List[Dict[str, Any]]:
    """
    Читает Excel-файл и для каждого листа возвращает:
    - name: имя листа
    - headers: заголовки (строка header_row_index, если >= 0, иначе авто A, B, C...)
    - sample_rows: первые preview_rows строк данных (формулы показываются как ⚡=FORMULA)
    """
    wb, tmp_path = _open_workbook(file_bytes)
    try:
        result = []
        for sheet_name in wb.sheet_names:
            sheet = wb.get_sheet_by_name(sheet_name)
            needed = (header_row_index + preview_rows + 1) if header_row_index >= 0 else preview_rows + 1
            all_values, all_formulas = _get_sheet_data_and_formulas(sheet, max_rows=needed)

            if not all_values:
                result.append({"name": sheet_name, "headers": [], "sample_rows": []})
                continue

            if header_row_index < 0:
                # Нет заголовков — авто A, B, C...
                max_cols = max(len(r) for r in all_values) if all_values else 0
                headers = _auto_generate_headers(max_cols)
                sample_rows = []
                for ri, row in enumerate(all_values[:preview_rows]):
                    fm = all_formulas[ri] if ri < len(all_formulas) else {}
                    sample_rows.append([
                        _format_preview_value(cell, fm.get(ci)) if cell is not None else ""
                        for ci, cell in enumerate(row)
                    ])
            else:
                header_fm = all_formulas[header_row_index] if header_row_index < len(all_formulas) else {}
                headers = [
                    _format_preview_value(cell, header_fm.get(ci)) if cell is not None else ""
                    for ci, cell in enumerate(all_values[header_row_index])
                ]
                sample_rows = []
                for ri in range(header_row_index + 1, header_row_index + preview_rows + 1):
                    if ri >= len(all_values):
                        break
                    fm = all_formulas[ri] if ri < len(all_formulas) else {}
                    sample_rows.append([
                        _format_preview_value(cell, fm.get(ci)) if cell is not None else ""
                        for ci, cell in enumerate(all_values[ri])
                    ])

            result.append({
                "name": sheet_name,
                "headers": headers,
                "sample_rows": sample_rows,
            })
        return result
    finally:
        _safe_unlink(tmp_path)


# =============================================================================
# ИМПОРТ
# =============================================================================

_BULK_BATCH_SIZE = 500


def _build_row_dicts(
    all_values: List[List[Any]],
    all_formulas: List[Dict[int, str]],
    data_start: int,
    merged_columns: List[Dict],
    style_remap: Dict[str, str],
    cell_style_keys: Dict[int, Dict[str, str]],
    xml_formulas: Dict[int, Dict[str, str]],
) -> List[Dict[str, Any]]:
    rows = []
    row_order = 0
    for ri, data_row in enumerate(all_values[data_start:]):
        if all(cell is None for cell in data_row):
            continue
        row_idx = data_start + ri
        fm = dict(all_formulas[row_idx]) if row_idx < len(all_formulas) else {}
        # XML-формулы применяются только для ячеек, где Calamine также определил
        # is_formula=True. Это отсекает "мёртвые" <f> элементы (оставшиеся после
        # редактирования, конвертации или некорректной выгрузки), которые в
        # импортированном датасете всё равно не работают из-за битых межлистовых
        # ссылок, а только засоряют строку формул.
        for col_letter, formula_str in xml_formulas.get(row_idx, {}).items():
            col_idx = _col_letter_to_index(col_letter)
            if col_idx in fm and col_idx < len(merged_columns):
                fm[col_idx] = formula_str
        data, formulas = _parse_row_with_formulas(data_row, merged_columns, fm)
        if not any(v for v in data.values() if v != "") and not formulas:
            continue
        cell_keys_old = cell_style_keys.get(row_idx, {})
        cell_keys = {cid: style_remap.get(key, key) for cid, key in cell_keys_old.items()}
        rows.append({
            "data": data,
            "formulas": formulas,
            "cell_styles": cell_keys,
            "row_order": row_order,
            "version": 1,
        })
        row_order += 1
    return rows


def _bulk_insert_rows(db: Session, dataset_id: int, sheet_id: str, row_dicts: List[Dict[str, Any]]):
    if not row_dicts:
        return
    for i in range(0, len(row_dicts), _BULK_BATCH_SIZE):
        batch = row_dicts[i:i + _BULK_BATCH_SIZE]
        for rd in batch:
            rd["dataset_id"] = dataset_id
            rd["sheet_id"] = sheet_id
        db.execute(insert(models.Row), batch)
    db.flush()


def _make_sub_sheets(processed_sheets: List[Dict]) -> List[Dict]:
    sub_sheets = []
    for ps in processed_sheets:
        entry = {
            "id": ps["sub_sheet_id"],
            "name": ps["sheet_name"],
            "order": len(sub_sheets),
            "frozen_rows": 0,
            "frozen_columns": 0,
        }
        meta = ps["sheet_metadata"]
        if meta:
            mc = meta.get("merged_cells")
            if mc:
                entry["merged_cells"] = mc
            cw = meta.get("column_widths")
            if cw:
                entry["column_widths"] = cw
            rh = meta.get("row_heights")
            if rh:
                entry["row_heights"] = rh
        sub_sheets.append(entry)
    return sub_sheets


def import_sheets_as_datasets(
    db: Session,
    user_id: int,
    file_bytes: bytes,
    sheet_names: List[str],
    header_row_index: int = 0,
    create_mode: str = "new",
    target_dataset_ids: Optional[List[int]] = None,
    filename: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Импортирует выбранные листы Excel в один датасет как под-листы (sub_sheets).
    """
    wb, tmp_path = _open_workbook(file_bytes)
    created_ids = []
    errors = []
    all_sheet_styles, all_sheet_metadata = _extract_styles_and_metadata(file_bytes)

    try:
        # --- First pass: collect data from all sheets ---
        processed_sheets = []
        merged_columns = []
        merged_col_ids = set()

        for idx, sheet_name in enumerate(sheet_names):
            try:
                if sheet_name not in wb.sheet_names:
                    errors.append(f"Лист '{sheet_name}' не найден в файле")
                    continue

                sheet = wb.get_sheet_by_name(sheet_name)
                all_values, all_formulas = _get_sheet_data_and_formulas(sheet)
                sheet_styles_dict = all_sheet_styles.get(sheet_name, {})
                style_map, cell_style_keys = _build_style_map(sheet_styles_dict)
                sheet_metadata = all_sheet_metadata.get(sheet_name, {})

                if header_row_index < 0:
                    max_cols = max(len(r) for r in all_values) if all_values else 0
                    headers = _auto_generate_headers(max_cols)
                    data_start = 0
                else:
                    if len(all_values) <= header_row_index:
                        errors.append(f"Лист '{sheet_name}' содержит меньше строк, чем индекс заголовка")
                        continue

                    header_row = all_values[header_row_index]
                    headers = [_normalize_value(cell) if cell is not None else "" for cell in header_row]
                    if all_values:
                        data_max_cols = max(len(r) for r in all_values)
                        while len(headers) < data_max_cols:
                            headers.append("")
                    if not headers or all(h == "" for h in headers):
                        errors.append(f"Лист '{sheet_name}': не найдено ни одного заголовка")
                        continue
                    data_start = header_row_index + 1

                sample_data = [list(r) for r in all_values[data_start:data_start + 101]]
                sheet_columns = _build_columns_from_headers(headers, sample_data)

                # Prefix column IDs for non-first sheets to avoid collisions
                if len(processed_sheets) > 0:
                    prefix = f"s{len(processed_sheets)}_"
                    for col in sheet_columns:
                        col["id"] = prefix + col["id"]

                for col in sheet_columns:
                    if col["id"] not in merged_col_ids:
                        merged_columns.append(col)
                        merged_col_ids.add(col["id"])

                sub_sheet_id = "main" if len(processed_sheets) == 0 else str(uuid.uuid4())

                processed_sheets.append({
                    "sub_sheet_id": sub_sheet_id,
                    "sheet_name": sheet_name,
                    "all_values": all_values,
                    "all_formulas": all_formulas,
                    "data_start": data_start,
                    "style_map": style_map,
                    "cell_style_keys": cell_style_keys,
                    "sheet_metadata": sheet_metadata,
                    "sheet_columns": sheet_columns,
                })
            except Exception as e:
                logger.error(f"Ошибка обработки листа '{sheet_name}'", error=str(e))
                errors.append(f"Лист '{sheet_name}': {str(e)}")

        if not processed_sheets:
            return {"created_datasets": created_ids, "errors": errors, "total_sheets_processed": len(sheet_names)}

        # Merge styles from all sheets (renumber keys to avoid conflicts)
        merged_styles = {}
        style_remaps = []
        for ps in processed_sheets:
            remap = {}
            for old_key, style_def in ps["style_map"].items():
                new_key = f"s{len(merged_styles)}"
                merged_styles[new_key] = style_def
                remap[old_key] = new_key
            style_remaps.append(remap)

        if create_mode == "new":
            if filename:
                ds_name = os.path.splitext(os.path.basename(filename))[0]
            else:
                ds_name = processed_sheets[0]["sheet_name"]

            existing = db.query(models.Dataset).filter(
                models.Dataset.name == ds_name,
                models.Dataset.owner_id == user_id,
                models.Dataset.archived == False,
            ).count()
            if existing > 0:
                ds_name = f"{ds_name} ({existing + 1})"

            dataset = models.Dataset(
                name=ds_name,
                owner_id=user_id,
                columns=merged_columns,
                header_row_1=None,
                header_row_2=None,
                header_row_2_colors=None,
                archived=False,
                styles=merged_styles,
                sub_sheets=_make_sub_sheets(processed_sheets),
            )
            db.add(dataset)
            db.flush()

            for si, ps in enumerate(processed_sheets):
                row_dicts = _build_row_dicts(
                    ps["all_values"], ps["all_formulas"], ps["data_start"],
                    merged_columns, style_remaps[si], ps["cell_style_keys"],
                    ps["sheet_metadata"].get("formulas", {}),
                )
                _bulk_insert_rows(db, dataset.id, ps["sub_sheet_id"], row_dicts)

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
            dataset.styles = merged_styles
            dataset.sub_sheets = _make_sub_sheets(processed_sheets)
            db.flush()

            for si, ps in enumerate(processed_sheets):
                row_dicts = _build_row_dicts(
                    ps["all_values"], ps["all_formulas"], ps["data_start"],
                    merged_columns, style_remaps[si], ps["cell_style_keys"],
                    ps["sheet_metadata"].get("formulas", {}),
                )
                _bulk_insert_rows(db, dataset.id, ps["sub_sheet_id"], row_dicts)

            db.commit()
            db.refresh(dataset)
            created_ids.append(dataset.id)

        else:
            raise ValueError(f"Неизвестный режим импорта: {create_mode}")

    except Exception as e:
        logger.error("Ошибка импорта Excel", error=str(e))
        errors.append(str(e))
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        _safe_unlink(tmp_path)

    return {
        "created_datasets": created_ids,
        "errors": errors,
        "total_sheets_processed": len(sheet_names),
    }
