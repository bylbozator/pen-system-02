import io
import re
from typing import List, Dict, Any, Optional
import pdfplumber
import structlog

logger = structlog.get_logger()

# --- Russian number words parser ---

_RUSSIAN_NUMBERS = {
    'ноль': 0,
    'один': 1, 'одна': 1, 'одно': 1, 'одну': 1, 'одни': 1,
    'два': 2, 'две': 2,
    'три': 3,
    'четыре': 4,
    'пять': 5,
    'шесть': 6,
    'семь': 7,
    'восемь': 8,
    'девять': 9,
    'десять': 10,
    'одиннадцать': 11,
    'двенадцать': 12,
    'тринадцать': 13,
    'четырнадцать': 14,
    'пятнадцать': 15,
    'шестнадцать': 16,
    'семнадцать': 17,
    'восемнадцать': 18,
    'девятнадцать': 19,
    'двадцать': 20,
    'тридцать': 30,
    'сорок': 40,
    'пятьдесят': 50,
    'шестьдесят': 60,
    'семьдесят': 70,
    'восемьдесят': 80,
    'девяносто': 90,
    'сто': 100,
    'двести': 200,
    'триста': 300,
    'четыреста': 400,
    'пятьсот': 500,
    'шестьсот': 600,
    'семьсот': 700,
    'восемьсот': 800,
    'девятьсот': 900,
}

_RUSSIAN_MULTIPLIERS = {
    'тысяча': 1000, 'тысячи': 1000, 'тысяч': 1000, 'тысячу': 1000,
    'миллион': 1_000_000, 'миллиона': 1_000_000, 'миллионов': 1_000_000,
}

_MEASURE_UNITS = {
    'штук', 'штука', 'штуки',
    'метр', 'метра', 'метров',
    'тонн', 'тонна', 'тонны',
    'килограмм', 'килограмма', 'килограммов',
    'кило',
    'кубометр', 'кубометра', 'кубометров',
    'куб', 'куба', 'кубов',
    'литр', 'литра', 'литров',
    'комплект', 'комплекта', 'комплектов',
    'рулон', 'рулона', 'рулонов',
    'пачк', 'пачки', 'пачек',
    'квадрат', 'квадрата', 'квадратов', 'квадратных', 'квадратный',
    'мешок', 'мешка', 'мешков',
    'патрон', 'патрона', 'патронов',
}

_INVOICE_NOISE = {
    'приняли', 'принято', 'принят', 'принята', 'приняла', 'принял',
    'поступило', 'поступили', 'поступила', 'поступил',
    'оприходовано', 'оприходован',
    'получено', 'получен', 'получена', 'получили', 'получил',
    'доставка', 'доставили', 'доставлено',
    'прибыло', 'прибыли',
    'приёмкой', 'оформлено',
    'завезли', 'завезено',
    'поставка', 'поставлено',
    'приход', 'приходит', 'пришёл', 'пришла',
    'привезли',
    'склад',
    '—', '–', '-',
}

_DATE_RE = re.compile(r'(\d{2}\.\d{2}\.\d{4})')
_TOKEN_RE = re.compile(r'[а-яёА-ЯЁa-zA-Z0-9]+(?:[-\/][а-яёА-ЯЁa-zA-Z0-9]+)*|[–—\-]')
_ENTRY_SPLIT_RE = re.compile(r'\.\s+(?=[А-ЯA-Z0-9])')


def parse_russian_number(words: List[str]) -> Optional[int]:
    total = 0
    current = 0
    for word in words:
        w = word.lower().strip('.,;:!?')
        if w in ('и',):
            continue
        if w in _RUSSIAN_MULTIPLIERS:
            mult = _RUSSIAN_MULTIPLIERS[w]
            if current == 0:
                current = 1
            total += current * mult
            current = 0
        elif w in _RUSSIAN_NUMBERS:
            num = _RUSSIAN_NUMBERS[w]
            if num >= 100:
                if current == 0:
                    current = num
                else:
                    current += num
            else:
                current += num
        else:
            return None
    total += current
    return total


def _split_invoice_entries(text: str) -> List[str]:
    text = re.sub(r'\s+', ' ', text).strip()
    parts = _ENTRY_SPLIT_RE.split(text)
    return [p.strip().rstrip('.') for p in parts if _DATE_RE.search(p)]


def _parse_invoice_entry(entry: str) -> Optional[Dict[str, Any]]:
    entry = entry.strip().rstrip('.')
    date_match = _DATE_RE.search(entry)
    if not date_match:
        return None

    date_str = date_match.group(1)
    after_date = entry[date_match.end():].strip()

    tokens = [(m.group(), m.start(), m.end()) for m in _TOKEN_RE.finditer(after_date)]
    if not tokens:
        return None

    q_start = 0
    while q_start < len(tokens):
        w = tokens[q_start][0].lower()
        if w in _INVOICE_NOISE or w in ('—', '–', '-'):
            q_start += 1
        else:
            break

    q_end = q_start
    while q_end < len(tokens):
        w = tokens[q_end][0].lower().strip('.,;:!?')
        if w in _RUSSIAN_NUMBERS or w in _RUSSIAN_MULTIPLIERS or w == 'и':
            q_end += 1
        else:
            break

    if q_start >= q_end:
        return None

    number_tokens = [t[0] for t in tokens[q_start:q_end]]
    quantity = parse_russian_number(number_tokens)
    if quantity is None:
        return None

    remaining_start = tokens[q_end - 1][2]
    remaining = after_date[remaining_start:].strip()
    remaining = re.sub(r'^[–—\-]\s*', '', remaining).strip()

    unit = None
    item_text = remaining

    unit_match = re.match(r'([а-яёА-ЯЁ]+)', remaining)
    if unit_match and unit_match.group(1).lower() in _MEASURE_UNITS:
        unit = unit_match.group(1).lower()
        item_text = remaining[unit_match.end():].strip()
        # Check for compound unit: "квадратных метров"
        next_match = re.match(r'([а-яёА-ЯЁ]+)', item_text)
        if next_match and next_match.group(1).lower() in _MEASURE_UNITS:
            compound = unit + ' ' + next_match.group(1).lower()
            if compound in ('квадратных метров', 'квадратный метр', 'квадратных метра'):
                unit = compound
                item_text = item_text[next_match.end():].strip()

    if unit is None:
        unit = 'штук'

    return {
        'date': date_str,
        'quantity': quantity,
        'unit': unit,
        'item': item_text,
        'raw': entry,
    }


def extract_invoice_records(text: str) -> List[Dict[str, Any]]:
    records = []
    for entry in _split_invoice_entries(text):
        rec = _parse_invoice_entry(entry)
        if rec:
            records.append(rec)
    return records


# --- Original PDF functions ---

def extract_text_from_pdf(file_bytes: bytes) -> str:
    text_parts = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return '\n'.join(text_parts)


def search_keywords(text: str, keywords: List[str]) -> List[Dict[str, Any]]:
    results = []
    for kw in keywords:
        pattern = re.compile(re.escape(kw), re.IGNORECASE)
        matches = []
        for m in pattern.finditer(text):
            start = max(0, m.start() - 60)
            end = min(len(text), m.end() + 60)
            context = text[start:end].replace('\n', ' ').strip()
            matches.append({
                "keyword": kw,
                "position": m.start(),
                "context": context,
            })
        if matches:
            results.append({
                "keyword": kw,
                "count": len(matches),
                "matches": matches,
            })
    return results


def extract_tables(file_bytes: bytes) -> List[Dict[str, Any]]:
    tables = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            page_tables = page.extract_tables()
            for table_idx, table in enumerate(page_tables):
                if not table or len(table) < 2:
                    continue
                headers = [c.strip() if c else '' for c in table[0]]
                rows = []
                for row in table[1:]:
                    rows.append([c.strip() if c else '' for c in row])
                tables.append({
                    "page": page_num + 1,
                    "index": len(tables),
                    "headers": headers,
                    "rows": rows,
                    "row_count": len(rows),
                })
    return tables


def extract_structured_data(
    file_bytes: bytes,
    keywords: Optional[List[str]] = None,
) -> Dict[str, Any]:
    text = extract_text_from_pdf(file_bytes)
    result: Dict[str, Any] = {
        "text": text,
        "text_length": len(text),
        "tables": [],
        "keyword_results": [],
    }

    tables = extract_tables(file_bytes)
    result["tables"] = tables

    if keywords:
        result["keyword_results"] = search_keywords(text, keywords)

    return result
