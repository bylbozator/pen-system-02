import re
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger()

# ── Pattern definitions ─────────────────────────────────────────────
# (regex, role_if_plan, role_if_fact, role_if_unknown, weight)
# Если role_if_plan == role_if_fact == role_if_unknown — роль не зависит от типа таблицы.
# weight: 100 = точное совпадение, меньше = менее специфичное.

PATTERNS: List[Tuple[str, str, str, str, int]] = [
    # ═══════════ Group (material name) ═══════════
    (r"полное наименование материала", "group", "group", "group", 100),
    (r"наименование материала\b", "group", "group", "group", 95),
    (r"наименование в спецификации", "group", "group", "group", 90),
    (r"\bматериал\b", "group", "group", "group", 50),
    (r"наименование\b", "group", "group", "group", 40),

    # ═══════════ Direction / Category ═══════════
    (r"направлени[ея]\s*использования?", "direction", "direction", "direction", 100),
    (r"направлени[ея]\b", "direction", "direction", "direction", 80),
    (r"\bкатегори[яи]\b", "direction", "direction", "direction", 60),

    # ═══════════ Budget ═══════════
    (r"спп-элемент", "budget", "budget", "budget", 100),
    (r"спп элемент", "budget", "budget", "budget", 100),
    (r"элемент бюджета", "budget", "budget", "budget", 90),

    # ═══════════ Unit (ЕИ) ═══════════
    (r"\bеи\b", "unit", "unit", "unit", 100),
    (r"еи в спецификации", "unit", "unit", "unit", 100),
    (r"единица измерения", "unit", "unit", "unit", 80),
    (r"ед\.?\s*изм", "unit", "unit", "unit", 90),
    (r"\bед\b(?!\s*изм)", "unit", "unit", "unit", 50),

    # ═══════════ Date / Month / Year ═══════════
    (r"месяц потребности", "date_plan", "date_plan", "date_plan", 100),
    (r"дата потребности", "date_plan", "date_plan", "date_plan", 100),
    (r"дата поступления", "date_actual", "date_actual", "date_actual", 100),
    (r"дата поставки", "date_actual", "date_actual", "date_actual", 100),
    (r"период\b", "date_plan", "date_actual", "date_plan", 50),
    (r"\bгод\b", "year", "year", "year", 80),
    (r"\bмесяц\b", "month", "month", "month", 70),

    # ═══════════ Quantity ═══════════
    # Plan-specific quantity
    (r"кол-во по потребности\b(?!\s*в спецификации)", "plan_qty", None, "plan_qty", 100),
    (r"количество по потребности\b(?!\s*в спецификации)", "plan_qty", None, "plan_qty", 95),
    # Fact-specific quantity
    (r"кол-во по потребности в спецификации", None, "actual_qty", "actual_qty", 100),
    (r"кол-во по спецификаци", None, "actual_qty", "actual_qty", 95),
    (r"кол-во пр спецификаций", None, "actual_qty", "actual_qty", 85),
    # Generic quantity → распределяется по типу таблицы
    (r"\bкол-во\b", "plan_qty", "actual_qty", "plan_qty", 25),
    (r"\bколичество\b", "plan_qty", "actual_qty", "plan_qty", 20),

    # ═══════════ Cost ═══════════
    # Specific actual cost (с "без НДС" — всегда факт)
    (r"стоимость,?\s*руб\.?\s*без\s*ндс", None, "actual_cost", "actual_cost", 100),
    (r"цена,?\s*руб\.?\s*без\s*ндс", None, "actual_cost", "actual_cost", 90),
    # Стоимость/цена с руб — если нет "без НДС", то план
    (r"стоимость,?\s*руб\.?(?!\s*без)", "plan_cost", "actual_cost", "plan_cost", 90),
    (r"цена,?\s*руб\.?(?!\s*без)", "plan_cost", "actual_cost", "plan_cost", 85),
    # Generic cost
    (r"\bстоимость\b", "plan_cost", "actual_cost", "plan_cost", 55),
    (r"\bцена\b", "plan_cost", "actual_cost", "plan_cost", 40),
    (r"\bсумм[аы]\b", "plan_cost", "actual_cost", "plan_cost", 20),

    # ═══════════ Other ═══════════
    (r"ном\.?\s*№", "order_num", "order_num", "order_num", 100),
    (r"№ заявки", "order_num", "order_num", "order_num", 100),
    (r"подразделение", "department", "department", "department", 80),
    (r"состояние\b", "status", "status", "status", 100),
]

# Роли, которые всегда участвуют в маппинге для отчёта
REPORT_ROLES = ["plan_qty", "plan_cost", "actual_qty", "actual_cost", "group", "direction", "budget", "unit"]

# Роли, специфичные для плана / факта
PLAN_ROLES = {"plan_qty", "plan_cost", "date_plan", "unit_plan"}
FACT_ROLES = {"actual_qty", "actual_cost", "date_actual", "unit_actual"}
SHARED_ROLES = {"group", "direction", "budget", "unit", "order_num", "department", "status", "date_plan", "date_actual", "year", "month"}


# ═══════════════════════════════════════════════════════════════════
# TABLE TYPE DETECTION
# ═══════════════════════════════════════════════════════════════════

def detect_table_type(headers: List[str]) -> str:
    combined = " ".join(h.lower() for h in headers if h)
    plan_score = 0
    fact_score = 0

    if "заявлено к приобретению" in combined:
        plan_score += 100
    if "исполнение" in combined:
        fact_score += 100
    if "месяц потребности" in combined:
        plan_score += 30
    if "кол-во по потребности" in combined and "в спецификации" not in combined:
        plan_score += 20
    if "цена, руб. без ндс" in combined or "стоимость, руб. без ндс" in combined:
        fact_score += 30
    if "дата поступления" in combined or "дата поставки" in combined:
        fact_score += 30
    if "кол-во по спецификации" in combined:
        fact_score += 20

    if plan_score > fact_score:
        return "plan"
    elif fact_score > plan_score:
        return "fact"
    return "unknown"


# ═══════════════════════════════════════════════════════════════════
# SCORING
# ═══════════════════════════════════════════════════════════════════

def _resolve_role(role_plan: Optional[str], role_fact: Optional[str], role_unknown: Optional[str], table_type: str) -> Optional[str]:
    """Выбирает правильное имя роли в зависимости от типа таблицы."""
    if table_type == "plan":
        return role_plan
    elif table_type == "fact":
        return role_fact
    else:
        return role_unknown


def _score_columns(columns: List[dict], table_type: str) -> Dict[str, List[Tuple[str, int]]]:
    """Для каждой роли собирает список (column_id, weight) подходящих колонок."""
    role_scores: Dict[str, List[Tuple[str, int]]] = {}
    for col in columns:
        col_id = col.get("id", "")
        header = (col.get("header", "") or "").lower()
        for pattern, role_p, role_f, role_u, weight in PATTERNS:
            if not re.search(pattern, header):
                continue
            role = _resolve_role(role_p, role_f, role_u, table_type)
            if role is None:
                continue
            role_scores.setdefault(role, []).append((col_id, weight))
    return role_scores


def _pick_best(role_scores: Dict[str, List[Tuple[str, int]]], role: str) -> Optional[str]:
    """Выбирает лучшую колонку для роли (макс вес, при равенстве — лекс. порядок)."""
    candidates = role_scores.get(role, [])
    if not candidates:
        return None
    candidates.sort(key=lambda x: (-x[1], x[0]))
    return candidates[0][0]


# ═══════════════════════════════════════════════════════════════════
# PER-DATASET SUGGESTIONS
# ═══════════════════════════════════════════════════════════════════

SUPPORTED_ROLES = ["plan_qty", "plan_cost", "actual_qty", "actual_cost", "group", "direction", "budget", "unit", "year", "month"]


def suggest_for_dataset(dataset) -> Dict[str, Any]:
    columns = dataset.columns or []
    headers = [col.get("header", "") or "" for col in columns]
    table_type = detect_table_type(headers)

    logger.info("column_detection.suggest_for_dataset",
                dataset_id=dataset.id, name=dataset.name,
                table_type=table_type, num_columns=len(columns))

    role_scores = _score_columns(columns, table_type)

    suggestions: Dict[str, Any] = {}
    for role in SUPPORTED_ROLES:
        suggestions[role] = _pick_best(role_scores, role)

    # ── Разрешение конфликтов ──

    # 1. plan_qty vs actual_qty: если одна колонка определена и как plan_qty, и как actual_qty
    plan_qty_col = suggestions.get("plan_qty")
    actual_qty_col = suggestions.get("actual_qty")
    if plan_qty_col and plan_qty_col == actual_qty_col:
        if table_type == "plan":
            suggestions["actual_qty"] = None
        elif table_type == "fact":
            suggestions["plan_qty"] = None
        else:
            suggestions["actual_qty"] = None

    # 2. plan_cost vs actual_cost: если одна колонка определена и как plan_cost, и как actual_cost
    plan_cost_col = suggestions.get("plan_cost")
    actual_cost_col = suggestions.get("actual_cost")
    if plan_cost_col and plan_cost_col == actual_cost_col:
        if table_type == "plan":
            suggestions["actual_cost"] = None
        elif table_type == "fact":
            suggestions["plan_cost"] = None
        else:
            suggestions["actual_cost"] = None

    # 3. Если тип таблицы "plan" — убираем actual_* роли (они не имеют смысла)
    #    Если тип "fact" — убираем plan_* роли
    if table_type == "plan":
        suggestions["actual_qty"] = None
        suggestions["actual_cost"] = None
        suggestions["unit"] = None  # для план-таблиц ЕИ показываем как unit_plan на фронте
    elif table_type == "fact":
        suggestions["plan_qty"] = None
        suggestions["plan_cost"] = None
    elif not suggestions.get("unit"):
        # Если тип не определён, но unit не найден — всё равно оставляем как есть
        pass

    # Добавляем тип таблицы в ответ для отображения на фронте
    suggestions["_table_type"] = table_type

    logger.info("column_detection.suggestions", dataset_id=dataset.id, name=dataset.name,
                suggestions=suggestions)

    return suggestions


# ═══════════════════════════════════════════════════════════════════
# BATCH SUGGESTIONS
# ═══════════════════════════════════════════════════════════════════

def suggest_mappings(datasets_list: list) -> Dict[str, dict]:
    result = {}
    for ds in datasets_list:
        suggestions = suggest_for_dataset(ds)
        result[str(ds.id)] = suggestions
    return result
