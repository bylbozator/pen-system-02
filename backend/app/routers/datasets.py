# backend/app/routers/datasets.py

from fastapi import APIRouter, Depends, HTTPException, Query, Path, Response
from sqlalchemy.orm import Session
from typing import List, Optional
from sqlalchemy import func, Numeric, cast, inspect as sa_inspect
import re
import json

from app.services.column_detection_service import suggest_mappings

from app import models, schemas, auth, dependencies
from app.database import get_db
from app.services.audit_service import log_action
from app.utils import dataset_to_out
from fastapi_cache import FastAPICache
import structlog

def _batch_delete(db: Session, model, filter_field, filter_value, batch_size=5000):
    pk = sa_inspect(model).primary_key[0]
    while True:
        ids = db.query(model).filter(filter_field == filter_value).with_entities(pk).limit(batch_size).all()
        if not ids:
            break
        pk_values = [row[0] for row in ids]
        db.query(model).filter(pk.in_(pk_values)).delete(synchronize_session=False)
        db.commit()


router = APIRouter(prefix="/api/datasets", tags=["datasets"], redirect_slashes=False)
logger = structlog.get_logger()

# ========================= ЭНДПОИНТЫ =========================

@router.post("/", response_model=schemas.DatasetOut, status_code=201)
def create_dataset(
    dataset_data: schemas.DatasetCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """
    Создание нового датасета.
    Если указан schema_id, колонки и header_rows копируются из схемы.
    Иначе датасет создаётся с пустой структурой (администратор может настроить позже).
    """
    columns = []
    header_row_1 = None
    header_row_2 = None
    header_row_2_colors = None

    # Если указана схема — копируем из неё
    if dataset_data.schema_id:
        schema = db.query(models.DatasetSchema).filter(models.DatasetSchema.id == dataset_data.schema_id).first()
        if not schema:
            raise HTTPException(status_code=404, detail="Схема не найдена")
        columns = schema.columns
        header_row_1 = schema.header_row_1
        header_row_2 = schema.header_row_2
        header_row_2_colors = schema.header_row_2_colors

    # Если схема не указана, создаём 10 колонок по умолчанию (A-J)
    if not columns:
        columns = [
            {"id": chr(65 + i), "header": chr(65 + i), "type": "string", "editableBy": []}
            for i in range(10)
        ]

    # Проверяем уникальность имени среди всех датасетов (включая архивные)
    existing = db.query(models.Dataset).filter(
        models.Dataset.name == dataset_data.name
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Датасет с названием '{dataset_data.name}' уже существует")

    db_dataset = models.Dataset(
        name=dataset_data.name,
        owner_id=current_user.id,
        schema_id=dataset_data.schema_id,
        columns=columns,
        header_row_1=header_row_1,
        header_row_2=header_row_2,
        header_row_2_colors=header_row_2_colors,
        row_filter=dataset_data.row_filter,
        unique_columns=dataset_data.unique_columns,
        default_sort_column=dataset_data.default_sort_column,
        default_sort_order=dataset_data.default_sort_order or "asc",
        sub_sheets=[s.model_dump() for s in (dataset_data.sub_sheets or [])] if dataset_data.sub_sheets else None,
        archived=False
    )

    db.add(db_dataset)
    db.commit()
    db.refresh(db_dataset)

    log_action(db, current_user.id, "CREATE_DATASET", "DATASET", str(db_dataset.id),
               {"name": dataset_data.name, "schema_id": dataset_data.schema_id})

    return dataset_to_out(db_dataset, db)


@router.get("/", response_model=schemas.DatasetsListResponse)
def list_datasets(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    include_archived: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    query = db.query(models.Dataset)

    if not include_archived:
        query = query.filter(models.Dataset.archived == False)

    if not auth.has_permission(current_user, "full_access", db) and \
       not auth.has_permission(current_user, "can_view_all_datasets", db):
        query = query.filter(models.Dataset.owner_id == current_user.id)

    total = query.count()
    datasets = query.order_by(models.Dataset.created_at.desc()).offset(skip).limit(limit).all()

    items = [dataset_to_out(ds, db) for ds in datasets]
    return schemas.DatasetsListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/report/suggest-columns")
def suggest_report_columns(
    dataset_ids: List[int] = Query(..., description="ID датасетов"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    ids = list(set(dataset_ids))
    datasets_list = db.query(models.Dataset).filter(
        models.Dataset.id.in_(ids),
        models.Dataset.archived == False
    ).all()
    if not datasets_list:
        raise HTTPException(status_code=404, detail="Датасеты не найдены")

    col_map = {}
    for ds in datasets_list:
        for col in (ds.columns or []):
            cid = col.get("id", "")
            if cid and cid not in col_map:
                header = col.get("header", "") or ""
                # Если заголовок совпадает с ID — значит колонка без реального имени,
                # показываем "Колонка X" вместо "X"
                if not header or header == cid:
                    header = f"Колонка {cid}"
                col_map[cid] = header

    suggestions = suggest_mappings(datasets_list)

    return {
        "suggestions": suggestions,
        "col_map": col_map,
    }


@router.get("/report")
def get_report(
    dataset_ids: List[int] = Query(..., description="ID датасетов"),
    plan_qty_col: Optional[str] = Query(None, description="Колонка кол-ва план"),
    plan_cost_col: Optional[str] = Query(None, description="Колонка стоимости план"),
    actual_qty_col: Optional[str] = Query(None, description="Колонка кол-ва факт"),
    actual_cost_col: Optional[str] = Query(None, description="Колонка стоимости факт"),
    group_col: Optional[str] = Query(None, description="Колонка для группировки"),
    group_col2: Optional[str] = Query(None, description="Вторая колонка группировки"),
    filter_col: Optional[str] = Query(None, description="Колонка фильтра"),
    filter_val: Optional[str] = Query(None, description="Значение фильтра"),
    search: Optional[str] = Query(None, description="Поиск по материалу"),
    direction_col: Optional[str] = Query(None, description="Колонка направления для фильтра"),
    budget_col: Optional[str] = Query(None, description="Колонка бюджета для фильтра"),
    unit_col: Optional[str] = Query(None, description="Колонка единицы измерения"),
    year_col: Optional[str] = Query(None, description="Колонка года"),
    month_col: Optional[str] = Query(None, description="Колонка месяца"),
    group_by: Optional[str] = Query("material", description="Тип группировки: material, category, month"),
    year_filter: Optional[int] = Query(None, description="Фильтр по году"),
    include_rows: bool = Query(False, description="Включить строки в ответ"),
    auto_map: bool = Query(False, description="Автоопределение колонок по заголовкам"),
    mappings_json: Optional[str] = Query(None, description="JSON c маппингом колонок для каждого датасета"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    ids = list(set(dataset_ids))
    datasets_list = db.query(models.Dataset).filter(
        models.Dataset.id.in_(ids),
        models.Dataset.archived == False
    ).all()
    if not datasets_list:
        raise HTTPException(status_code=404, detail="Датасеты не найдены")

    col_map = {}
    for ds in datasets_list:
        for col in (ds.columns or []):
            cid = col.get("id", "")
            if cid and cid not in col_map:
                header = col.get("header", "") or ""
                if not header or header == cid:
                    header = f"Колонка {cid}"
                col_map[cid] = header

    # ── Per-dataset column mappings ──────────────────────────────────
    per_ds_mapping: dict = {}

    if mappings_json:
        try:
            per_ds_mapping = json.loads(mappings_json)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Некорректный JSON в mappings_json")
    elif auto_map:
        per_ds_mapping = suggest_mappings(datasets_list)
    else:
        # Единый маппинг для всех датасетов (старое поведение)
        default_map = {
            "plan_qty": plan_qty_col or "S",
            "plan_cost": plan_cost_col or "T",
            "actual_qty": actual_qty_col or "AR",
            "actual_cost": actual_cost_col or "AT",
            "group": group_col or "A",
            "direction": direction_col or "A",
            "budget": budget_col or "B",
            "unit": unit_col or "",
            "year": year_col or "",
            "month": month_col or "",
        }
        for ds in datasets_list:
            per_ds_mapping[str(ds.id)] = dict(default_map)

    # Для единого маппинга (старое поведение) берём из первого датасета
    first_map = per_ds_mapping.get(str(datasets_list[0].id), {})
    effective_cols = {
        "plan_qty": first_map.get("plan_qty") or plan_qty_col or "S",
        "plan_cost": first_map.get("plan_cost") or plan_cost_col or "T",
        "actual_qty": first_map.get("actual_qty") or actual_qty_col or "AR",
        "actual_cost": first_map.get("actual_cost") or actual_cost_col or "AT",
        "group": first_map.get("group") or group_col or "A",
        "direction": first_map.get("direction") or direction_col or "A",
        "budget": first_map.get("budget") or budget_col or "B",
        "unit": first_map.get("unit") or unit_col or "",
        "year": first_map.get("year") or year_col or "",
        "month": first_map.get("month") or month_col or "",
    }

    def safe_float(v):
        if v is None: return 0.0
        try: return float(v)
        except (ValueError, TypeError): return 0.0

    def get_col(row, col_id):
        return row.data.get(col_id) if row.data else None

    def parse_year(val) -> Optional[int]:
        if val is None: return None
        try: return int(str(val).strip()[:4])
        except: return None

    def parse_month(val) -> Optional[int]:
        if val is None: return None
        s = str(val).strip().lower()
        month_map = {
            "январь": 1, "янв": 1,
            "февраль": 2, "фев": 2,
            "март": 3,
            "апрель": 4, "апр": 4,
            "май": 5,
            "июнь": 6,
            "июль": 7,
            "август": 8, "авг": 8,
            "сентябрь": 9, "сен": 9,
            "октябрь": 10, "окт": 10,
            "ноябрь": 11, "ноя": 11,
            "декабрь": 12, "дек": 12,
        }
        if s in month_map:
            return month_map[s]
        try:
            m = int(re.search(r'\d+', s).group())
            if 1 <= m <= 12: return m
        except: pass
        return None

    # ── Normalize rows from all datasets using per-dataset mapping ──
    all_normalized = []

    for ds in datasets_list:
        ds_id = str(ds.id)
        mapping = per_ds_mapping.get(ds_id, effective_cols)

        rows = db.query(models.Row).filter(
            models.Row.dataset_id == ds.id
        ).order_by(models.Row.row_order).all()

        for row in rows:
            raw_unit = str(get_col(row, mapping.get("unit", "")) or "").strip()
            year_val = parse_year(get_col(row, mapping.get("year", "")))
            month_val = parse_month(get_col(row, mapping.get("month", "")))
            # Fallback: try to extract year/month from date columns
            if year_val is None:
                for date_key in ("date_plan", "date_actual"):
                    dc = mapping.get(date_key)
                    if dc:
                        year_val = parse_year(get_col(row, dc))
                        if year_val: break
            if month_val is None:
                for date_key in ("date_plan", "date_actual"):
                    dc = mapping.get(date_key)
                    if dc:
                        month_val = parse_month(get_col(row, dc))
                        if month_val: break

            normalized = {
                "plan_qty": safe_float(get_col(row, mapping.get("plan_qty", ""))),
                "plan_cost": safe_float(get_col(row, mapping.get("plan_cost", ""))),
                "actual_qty": safe_float(get_col(row, mapping.get("actual_qty", ""))),
                "actual_cost": safe_float(get_col(row, mapping.get("actual_cost", ""))),
                "group_val": str(get_col(row, mapping.get("group", "")) or "(пусто)"),
                "direction_val": str(get_col(row, mapping.get("direction", "")) or ""),
                "budget_val": str(get_col(row, mapping.get("budget", "")) or ""),
                "unit_val": raw_unit,
                "year_val": year_val,
                "month_val": month_val,
                "row_ref": row,
            }
            all_normalized.append(normalized)

    if not all_normalized:
        return {
            "columns": effective_cols,
            "summary": {"total_plan_qty": 0, "total_plan_cost": 0,
                       "total_actual_qty": 0, "total_actual_cost": 0,
                       "execution_pct_qty": 0, "execution_pct_cost": 0},
            "groups": [], "directions": [], "budget_elements": [], "col_map": col_map,
            "volume_by_uom": [], "trend": [], "top_volume": [],
        }

    # Собираем все направления/бюджеты ДО фильтрации, чтобы дропдауны не схлопывались
    all_directions = sorted(set(r["direction_val"] for r in all_normalized if r["direction_val"]))
    all_budget_elements = sorted(set(r["budget_val"] for r in all_normalized if r["budget_val"]))

    # ── Filters ──
    if filter_val:
        all_normalized = [r for r in all_normalized if (
            r.get("direction_val") == filter_val or r.get("budget_val") == filter_val
        )]

    if year_filter:
        all_normalized = [r for r in all_normalized if r.get("year_val") == year_filter]

    if search:
        s = search.lower()
        all_normalized = [r for r in all_normalized if s in r.get("group_val", "").lower()]

    # ── Aggregation ──
    from collections import defaultdict

    groups = {}
    for row in all_normalized:
        if group_by == "category":
            g_key = row.get("direction_val", "") or "(без категории)"
        elif group_by == "month":
            y = row.get("year_val") or 0
            m = row.get("month_val") or 0
            g_key = f"{y}-{m:02d}" if y and m else "(без даты)"
        else:
            g_key = row["group_val"]
            if group_col2:
                g2 = row.get("group_val2", "")
                if g2: g_key = f"{g_key} / {g2}"

        if g_key not in groups:
            groups[g_key] = {"name": g_key, "plan_qty": 0.0, "plan_cost": 0.0,
                            "actual_qty": 0.0, "actual_cost": 0.0, "count": 0,
                            "unit_map": defaultdict(float)}
        groups[g_key]["plan_qty"] += row["plan_qty"]
        groups[g_key]["plan_cost"] += row["plan_cost"]
        groups[g_key]["actual_qty"] += row["actual_qty"]
        groups[g_key]["actual_cost"] += row["actual_cost"]
        groups[g_key]["count"] += 1
        if row.get("unit_val"):
            groups[g_key]["unit_map"][row["unit_val"]] += row["actual_qty"]

    for g in groups.values():
        g["execution_pct_qty"] = round((g["actual_qty"] / g["plan_qty"] * 100) if g["plan_qty"] else 0, 1)
        g["execution_pct_cost"] = round((g["actual_cost"] / g["plan_cost"] * 100) if g["plan_cost"] else 0, 1)
        # Объём по ЕИ: [{"uom": "т", "qty": 120.0}, ...]
        g["volume"] = [{"uom": uom, "qty": round(qty, 2)} for uom, qty in
                       sorted(g.pop("unit_map", {}).items(), key=lambda x: -x[1])]

    groups_list = sorted(groups.values(), key=lambda x: x["name"])
    tp = sum(g["plan_qty"] for g in groups_list)
    tc = sum(g["plan_cost"] for g in groups_list)
    ap = sum(g["actual_qty"] for g in groups_list)
    ac = sum(g["actual_cost"] for g in groups_list)

    # ── Trend: накопленный факт по месяцам ──
    trend_map = defaultdict(lambda: {"plan_cost": 0.0, "actual_cost": 0.0, "actual_qty": 0.0})
    for row in all_normalized:
        y = row.get("year_val") or 0
        m = row.get("month_val") or 0
        if y and m:
            key = f"{y}-{m:02d}"
            trend_map[key]["plan_cost"] += row["plan_cost"]
            trend_map[key]["actual_cost"] += row["actual_cost"]
            trend_map[key]["actual_qty"] += row["actual_qty"]

    cumulative = 0.0
    trend = []
    for month_key in sorted(trend_map.keys()):
        cumulative += trend_map[month_key]["actual_cost"]
        trend.append({
            "month": month_key,
            "plan_cost": round(trend_map[month_key]["plan_cost"], 2),
            "actual_cost": round(trend_map[month_key]["actual_cost"], 2),
            "actual_qty": round(trend_map[month_key]["actual_qty"], 2),
            "cumulative_actual_cost": round(cumulative, 2),
        })

    # ── Топ-10 по объёму (реальному объёму в первой ЕИ) ──
    top_volume = sorted(
        [g for g in groups_list if g["volume"]],
        key=lambda g: g["volume"][0]["qty"] if g["volume"] else 0,
        reverse=True
    )[:10]
    top_volume_out = []
    for g in top_volume:
        first = g["volume"][0] if g["volume"] else {"uom": "", "qty": 0}
        top_volume_out.append({
            "name": g["name"],
            "volume_qty": first["qty"],
            "uom": first["uom"],
            "plan_cost": g["plan_cost"],
            "actual_cost": g["actual_cost"],
        })

    # ── Глобальный объём по всем ЕИ ──
    total_volume_map = defaultdict(float)
    for row in all_normalized:
        if row.get("unit_val"):
            total_volume_map[row["unit_val"]] += row["actual_qty"]
    volume_by_uom = [{"uom": uom, "qty": round(qty, 2)}
                     for uom, qty in sorted(total_volume_map.items(), key=lambda x: -x[1])]

    response_data = {
        "summary": {
            "total_plan_qty": round(tp, 2), "total_plan_cost": round(tc, 2),
            "total_actual_qty": round(ap, 2), "total_actual_cost": round(ac, 2),
            "execution_pct_qty": round((ap / tp * 100) if tp else 0, 1),
            "execution_pct_cost": round((ac / tc * 100) if tc else 0, 1),
            "total_rows": len(all_normalized),
            "volume_by_uom": volume_by_uom,
        },
        "groups": groups_list,
        "trend": trend,
        "top_volume": top_volume_out,
        "directions": all_directions,
        "budget_elements": all_budget_elements,
        "col_map": col_map,
        "columns": effective_cols,
    }

    if include_rows and all_normalized:
        max_report_rows = 500
        truncated = len(all_normalized) > max_report_rows
        response_data["rows"] = [
            {"id": r["row_ref"].id, "data": {
                "plan_qty": r["plan_qty"],
                "plan_cost": r["plan_cost"],
                "actual_qty": r["actual_qty"],
                "actual_cost": r["actual_cost"],
                "group": r["group_val"],
                "direction": r["direction_val"],
                "budget": r["budget_val"],
                "unit": r["unit_val"],
                "year": r["year_val"],
                "month": r["month_val"],
            }, "row_order": r["row_ref"].row_order}
            for r in all_normalized[:max_report_rows]
        ]
        response_data["truncated"] = truncated
        response_data["total_rows_matched"] = len(all_normalized)

    return response_data


@router.get("/report/trend")
def get_report_trend(
    dataset_ids: List[int] = Query(..., description="ID датасетов"),
    year_filter: Optional[int] = Query(None, description="Фильтр по году"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Накопленный факт по месяцам для выбранных датасетов."""
    ids = list(set(dataset_ids))
    datasets_list = db.query(models.Dataset).filter(
        models.Dataset.id.in_(ids),
        models.Dataset.archived == False
    ).all()
    if not datasets_list:
        raise HTTPException(status_code=404, detail="Датасеты не найдены")

    from collections import defaultdict
    import re

    def safe_float(v):
        if v is None: return 0.0
        try: return float(v)
        except: return 0.0

    def parse_month(val) -> Optional[int]:
        if val is None: return None
        s = str(val).strip().lower()
        mm = {"январь":1,"янв":1,"февраль":2,"фев":2,"март":3,"апрель":4,"апр":4,"май":5,"июнь":6,"июль":7,"август":8,"авг":8,"сентябрь":9,"сен":9,"октябрь":10,"окт":10,"ноябрь":11,"ноя":11,"декабрь":12,"дек":12}
        if s in mm: return mm[s]
        try:
            m = int(re.search(r'\d+', s).group())
            if 1<=m<=12: return m
        except: pass
        return None

    trend_map = defaultdict(lambda: {"plan_cost": 0.0, "actual_cost": 0.0, "actual_qty": 0.0})

    for ds in datasets_list:
        rows = db.query(models.Row).filter(models.Row.dataset_id == ds.id).all()
        for row in rows:
            data = row.data or {}
            for key, val in data.items():
                if val is None: continue
                if "цена" in str(val).lower() or "стоимость" in str(val).lower() or "сумм" in str(val).lower():
                    continue
            plan_cost = safe_float(data.get("T") or data.get("plan_cost", 0))
            actual_cost = safe_float(data.get("AT") or data.get("actual_cost", 0))
            actual_qty = safe_float(data.get("AR") or data.get("actual_qty", 0))

            month = None
            year = None
            for cid, val in data.items():
                sval = str(val).lower()
                if "месяц" in sval or "период" in sval:
                    month = parse_month(val)
                if "год" in sval or str(val).strip().isdigit() and len(str(val).strip()) == 4:
                    try:
                        y = int(str(val).strip()[:4])
                        if 2000 <= y <= 2100: year = y
                    except: pass

            if year_filter and year != year_filter:
                continue
            if month:
                mkey = f"{year or 0}-{month:02d}"
                trend_map[mkey]["plan_cost"] += plan_cost
                trend_map[mkey]["actual_cost"] += actual_cost
                trend_map[mkey]["actual_qty"] += actual_qty

    cumulative = 0.0
    result = []
    for mk in sorted(trend_map.keys()):
        cumulative += trend_map[mk]["actual_cost"]
        result.append({
            "month": mk,
            "plan_cost": round(trend_map[mk]["plan_cost"], 2),
            "actual_cost": round(trend_map[mk]["actual_cost"], 2),
            "actual_qty": round(trend_map[mk]["actual_qty"], 2),
            "cumulative_actual_cost": round(cumulative, 2),
        })
    return result


@router.get("/report/volume")
def get_report_volume(
    dataset_ids: List[int] = Query(..., description="ID датасетов"),
    group_by: str = Query("category", description="Группировка: category, material"),
    year_filter: Optional[int] = Query(None, description="Фильтр по году"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Реальный объём по категориям или материалам с разбивкой по ЕИ."""
    ids = list(set(dataset_ids))
    datasets_list = db.query(models.Dataset).filter(
        models.Dataset.id.in_(ids),
        models.Dataset.archived == False
    ).all()
    if not datasets_list:
        raise HTTPException(status_code=404, detail="Датасеты не найдены")

    from collections import defaultdict

    def safe_float(v):
        if v is None: return 0.0
        try: return float(v)
        except: return 0.0

    volume = defaultdict(lambda: defaultdict(float))

    for ds in datasets_list:
        rows = db.query(models.Row).filter(models.Row.dataset_id == ds.id).all()
        for row in rows:
            data = row.data or {}
            qty = safe_float(data.get("AR") or data.get("actual_qty", 0))
            uom = str(data.get("AI") or data.get("unit") or "").strip()
            category = str(data.get("A") or data.get("direction") or "").strip()
            material = str(data.get("B") or data.get("group") or "").strip()

            if group_by == "material":
                key = material or "(без названия)"
            else:
                key = category or "(без категории)"
            if uom:
                volume[key][uom] += qty

    result = []
    for key, uoms in sorted(volume.items()):
        uom_list = [{"uom": u, "qty": round(q, 2)} for u, q in sorted(uoms.items(), key=lambda x: -x[1])]
        total_qty = sum(u["qty"] for u in uom_list)
        result.append({
            "name": key,
            "total_qty": round(total_qty, 2),
            "uoms": uom_list,
        })
    result.sort(key=lambda x: -x["total_qty"])
    return result


# ========================= УПРАВЛЕНИЕ ЛИСТАМИ =========================
@router.get("/{dataset_id}/sheets")
def get_sheets(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=False))
):
    sheets = dataset.sub_sheets
    if not sheets:
        sheets = [{"id": "main", "name": "Лист1", "order": 0}]
    return {"sheets": sheets}


@router.post("/{dataset_id}/sheets", status_code=201)
def create_sheet(
    dataset_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=True))
):
    sheets = dataset.sub_sheets or []
    name = body.get("name", f"Лист{len(sheets) + 1}")
    import uuid
    new_id = str(uuid.uuid4())
    sheet = {"id": new_id, "name": name, "order": len(sheets),
             "frozen_rows": 0, "frozen_columns": 0, "merged_cells": [],
             "column_widths": None, "row_heights": None,
             "hidden_columns": [], "hidden_rows": []}
    sheets.append(sheet)
    dataset.sub_sheets = sheets
    db.commit()
    log_action(db, current_user.id, "CREATE_SHEET", "DATASET", str(dataset.id), {"sheet_id": new_id, "name": name})
    return {"ok": True, "sheet": sheet}


@router.delete("/{dataset_id}/sheets/{sheet_id}", status_code=204)
def delete_sheet(
    dataset_id: int,
    sheet_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=True))
):
    sheets = dataset.sub_sheets or []
    dataset.sub_sheets = [s for s in sheets if s.get("id") != sheet_id]
    # Удаляем строки этого листа
    db.query(models.Row).filter(
        models.Row.dataset_id == dataset_id,
        models.Row.sheet_id == sheet_id
    ).delete(synchronize_session=False)
    db.commit()
    log_action(db, current_user.id, "DELETE_SHEET", "DATASET", str(dataset.id), {"sheet_id": sheet_id})
    return Response(status_code=204)


@router.patch("/{dataset_id}/sheets/{sheet_id}")
def update_sheet(
    dataset_id: int,
    sheet_id: str,
    body: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=True))
):
    sheets = dataset.sub_sheets or []
    for s in sheets:
        if s.get("id") == sheet_id:
            if "name" in body:
                s["name"] = body["name"]
            if "frozen_rows" in body:
                s["frozen_rows"] = body["frozen_rows"]
            if "frozen_columns" in body:
                s["frozen_columns"] = body["frozen_columns"]
            if "merged_cells" in body:
                s["merged_cells"] = body["merged_cells"]
            if "column_widths" in body:
                s["column_widths"] = body["column_widths"]
            if "row_heights" in body:
                s["row_heights"] = body["row_heights"]
            if "hidden_columns" in body:
                s["hidden_columns"] = body["hidden_columns"]
            if "hidden_rows" in body:
                s["hidden_rows"] = body["hidden_rows"]
            if "order" in body:
                s["order"] = body["order"]
            if "group_rows" in body:
                s["group_rows"] = body["group_rows"]
            if "group_columns" in body:
                s["group_columns"] = body["group_columns"]
            break
    dataset.sub_sheets = sheets
    db.commit()
    log_action(db, current_user.id, "UPDATE_SHEET", "DATASET", str(dataset.id), {"sheet_id": sheet_id})
    return {"ok": True}


@router.get("/{dataset_id}", response_model=schemas.DatasetOut)
def get_dataset(
    dataset_id: int = Path(..., description="ID датасета"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=False))
):
    return dataset_to_out(dataset, db)


@router.patch("/{dataset_id}", response_model=schemas.DatasetOut)
def update_dataset_meta(
    dataset_id: int,
    update: schemas.DatasetUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=True))
):
    """
    Обновление метаданных (имя, фильтры, сортировка, но не структура колонок).
    Структуру колонок может менять только администратор через отдельный эндпоинт.
    """
    changes = {}

    if update.name is not None:
        existing = db.query(models.Dataset).filter(
            models.Dataset.name == update.name,
            models.Dataset.id != dataset_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Датасет с названием '{update.name}' уже существует")
        dataset.name = update.name
        changes["name"] = update.name

    if update.row_filter is not None:
        dataset.row_filter = update.row_filter
        changes["row_filter"] = update.row_filter

    if update.unique_columns is not None:
        dataset.unique_columns = update.unique_columns
        changes["unique_columns"] = update.unique_columns

    if update.default_sort_column is not None:
        dataset.default_sort_column = update.default_sort_column
        changes["default_sort_column"] = update.default_sort_column

    if update.default_sort_order is not None:
        dataset.default_sort_order = update.default_sort_order
        changes["default_sort_order"] = update.default_sort_order

    if update.sub_sheets is not None:
        dataset.sub_sheets = [s.model_dump() for s in update.sub_sheets]
        changes["sub_sheets"] = f"{len(update.sub_sheets)} sheets"

    if update.styles is not None:
        dataset.styles = update.styles
        changes["styles"] = f"{len(update.styles)} styles"

    db.commit()
    db.refresh(dataset)

    if changes:
        log_action(db, current_user.id, "UPDATE_DATASET_META", "DATASET", str(dataset.id), changes)

    return dataset_to_out(dataset, db)


@router.patch("/{dataset_id}/columns", response_model=schemas.DatasetOut)
def update_dataset_columns(
    dataset_id: int,
    columns_update: schemas.DatasetColumnsUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=True))
):
    """Изменение колонок таблицы (доступно всем активным пользователям)."""
    dataset.columns = [col.model_dump() if hasattr(col, 'model_dump') else col for col in columns_update.columns]

    db.commit()
    db.refresh(dataset)
    log_action(db, current_user.id, "UPDATE_DATASET_COLUMNS", "DATASET", str(dataset.id))
    return dataset_to_out(dataset, db)


@router.patch("/{dataset_id}/structure", response_model=schemas.DatasetOut)
def update_dataset_structure(
    dataset_id: int,
    structure: schemas.DatasetSchemaUpdate,  # используем ту же схему, что и для схем
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=True))
):
    """
    Изменение структуры колонок, строк итогов/групп.
    Доступно всем активным пользователям.
    """
    if structure.columns is not None:
        # Преобразуем ColumnDef в словари
        dataset.columns = [col.model_dump() if hasattr(col, 'model_dump') else col for col in structure.columns]
    if structure.header_row_1 is not None:
        dataset.header_row_1 = structure.header_row_1
    if structure.header_row_2 is not None:
        dataset.header_row_2 = structure.header_row_2
    if structure.header_row_2_colors is not None:
        dataset.header_row_2_colors = structure.header_row_2_colors

    db.commit()
    db.refresh(dataset)

    log_action(db, current_user.id, "UPDATE_DATASET_STRUCTURE", "DATASET", str(dataset.id),
               {"columns_updated": structure.columns is not None})
    return dataset_to_out(dataset, db)


@router.delete("/{dataset_id}", status_code=204)
def archive_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=True))
):
    """Мягкое удаление (архивация)."""
    dataset.archived = True
    db.commit()
    log_action(db, current_user.id, "ARCHIVE_DATASET", "DATASET", str(dataset.id), {"name": dataset.name})
    return Response(status_code=204)


@router.delete("/{dataset_id}/permanent", status_code=204)
async def permanent_delete_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    if not auth.has_permission(current_user, "full_access", db):
        raise HTTPException(status_code=403, detail="Только администратор может полностью удалять датасеты")

    dataset = db.query(models.Dataset).filter(models.Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Датасет не найден")
    if not dataset.archived:
        raise HTTPException(status_code=400, detail="Сначала переместите датасет в архив")

    name = dataset.name

    _batch_delete(db, models.CellHistory, models.CellHistory.dataset_id, dataset_id)
    _batch_delete(db, models.RowHistory, models.RowHistory.dataset_id, dataset_id)
    _batch_delete(db, models.CellComment, models.CellComment.dataset_id, dataset_id)
    _batch_delete(db, models.Row, models.Row.dataset_id, dataset_id)

    db.delete(dataset)
    db.commit()
    await FastAPICache.clear()
    log_action(db, current_user.id, "PERMANENT_DELETE_DATASET", "DATASET", str(dataset_id), {"name": name})
    return Response(status_code=204)


@router.post("/{dataset_id}/restore")
def restore_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Восстановление из архива (доступно всем активным пользователям)."""
    dataset = db.query(models.Dataset).filter(models.Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Датасет не найден")
    if not dataset.archived:
        raise HTTPException(status_code=400, detail="Датасет не в архиве")

    dataset.archived = False
    db.commit()
    log_action(db, current_user.id, "RESTORE_DATASET", "DATASET", str(dataset.id), {"name": dataset.name})
    return {"ok": True, "message": f"Датасет '{dataset.name}' восстановлен"}


@router.post("/{dataset_id}/duplicate", response_model=schemas.DatasetOut, status_code=201)
def duplicate_dataset(
    dataset_id: int,
    new_name: Optional[str] = Query(None, description="Новое название, иначе добавится ' (копия)'"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=False))  # для копирования нужен хотя бы просмотр
):
    """Создание копии датасета (доступно всем активным пользователям)."""
    target_name = new_name or f"{dataset.name} (копия)"
    existing = db.query(models.Dataset).filter(
        models.Dataset.name == target_name
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Датасет с названием '{target_name}' уже существует")

    new_dataset = models.Dataset(
        name=target_name,
        owner_id=current_user.id,
        columns=dataset.columns,
        header_row_1=dataset.header_row_1,
        header_row_2=dataset.header_row_2,
        header_row_2_colors=dataset.header_row_2_colors,
        row_filter=dataset.row_filter,
        unique_columns=dataset.unique_columns,
        default_sort_column=dataset.default_sort_column,
        default_sort_order=dataset.default_sort_order,
        schema_id=dataset.schema_id,
        sub_sheets=dataset.sub_sheets,
        archived=False
    )
    db.add(new_dataset)
    db.flush()

    # Копируем строки
    rows = db.query(models.Row).filter(models.Row.dataset_id == dataset.id).all()
    for row in rows:
        new_row = models.Row(
            dataset_id=new_dataset.id,
            sheet_id=row.sheet_id,
            data=row.data.copy() if row.data else {},
            formulas=row.formulas.copy() if row.formulas else {},
            cell_styles=row.cell_styles.copy() if row.cell_styles else {},
            row_order=row.row_order,
            version=1
        )
        db.add(new_row)

    db.commit()
    db.refresh(new_dataset)

    log_action(db, current_user.id, "DUPLICATE_DATASET", "DATASET", str(new_dataset.id),
               {"source_id": dataset_id, "new_name": target_name})
    return dataset_to_out(new_dataset, db)


@router.get("/{dataset_id}/header_row_1")
def get_header_row_1(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=False))
):
    """Вычисляемые итоги для первой строки (формулы)."""
    if not dataset.header_row_1:
        return {}

    # Базовый запрос с учётом фильтра
    query = db.query(models.Row).filter(models.Row.dataset_id == dataset_id)
    if not auth.has_permission(current_user, "full_access", db):
        query = dependencies.apply_row_filter(query, dataset, current_user, db)

    result = {}
    for col_id, formula in dataset.header_row_1.items():
        if not formula or not isinstance(formula, str):
            result[col_id] = None
            continue
        # Простая поддержка формул вида =SUBTOTAL(9, X4:X10000)
        match = re.match(r"=SUBTOTAL\(9,([A-Z]+)\d+:\1\d+\)", formula)
        if match:
            col_letter = match.group(1)
            total = query.with_entities(
                func.sum(cast(models.Row.data[col_letter].astext, Numeric))
            ).scalar()
            result[col_id] = float(total) if total is not None else 0.0
        else:
            result[col_id] = None  # другие формулы пока не поддерживаются
    return result


@router.get("/{dataset_id}/summary")
def get_dataset_summary(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=False))
):
    """Сводка по числовым колонкам (суммы)."""
    numeric_columns = [col["id"] for col in dataset.columns if col.get("type") == "number"]
    if not numeric_columns:
        return {}

    query = db.query(models.Row).filter(models.Row.dataset_id == dataset_id)
    if not auth.has_permission(current_user, "full_access", db):
        query = dependencies.apply_row_filter(query, dataset, current_user, db)

    result = {}
    for col_id in numeric_columns:
        sum_value = query.with_entities(
            func.sum(cast(models.Row.data[col_id].astext, Numeric))
        ).scalar()
        result[col_id] = float(sum_value) if sum_value is not None else 0.0
    return result


@router.get("/{dataset_id}/cond-formatting")
def get_cond_formatting(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=False))
):
    """Получить правила условного форматирования датасета."""
    return {"rules": dataset.conditional_formatting or []}


@router.put("/{dataset_id}/cond-formatting")
def save_cond_formatting(
    dataset_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=True))
):
    """Сохранить правила условного форматирования датасета."""
    dataset.conditional_formatting = body.get("rules", [])
    db.commit()
    log_action(db, current_user.id, "UPDATE_COND_FORMATTING", "DATASET", str(dataset.id))
    return {"ok": True}


@router.get("/{dataset_id}/stats")
def get_dataset_stats(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=False))
):
    """Статистика: количество строк, комментариев, последнее обновление."""
    row_query = db.query(models.Row).filter(models.Row.dataset_id == dataset_id)
    if not auth.has_permission(current_user, "full_access", db):
        row_query = dependencies.apply_row_filter(row_query, dataset, current_user, db)
    total_rows = row_query.count()

    total_comments = db.query(models.CellComment).filter(
        models.CellComment.dataset_id == dataset_id
    ).count()

    last_updated_row = db.query(models.Row).filter(
        models.Row.dataset_id == dataset_id
    ).order_by(models.Row.updated_at.desc()).first()
    last_updated = last_updated_row.updated_at if last_updated_row else dataset.created_at

    return {
        "total_rows": total_rows,
        "total_comments": total_comments,
        "last_updated": last_updated,
        "archived": dataset.archived,
        "owner_id": dataset.owner_id,
        "created_at": dataset.created_at
    }


# ========================= СОХРАНЁННЫЕ ФИЛЬТРЫ (FILTER VIEWS) =========================
@router.get("/{dataset_id}/filters", response_model=List[schemas.SavedFilterOut])
def list_saved_filters(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=False))
):
    filters = db.query(models.SavedFilter).filter(
        models.SavedFilter.dataset_id == dataset_id
    ).order_by(models.SavedFilter.created_at).all()
    return filters


@router.post("/{dataset_id}/filters", response_model=schemas.SavedFilterOut, status_code=201)
def create_saved_filter(
    dataset_id: int,
    body: schemas.SavedFilterCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=True))
):
    if body.is_default:
        db.query(models.SavedFilter).filter(
            models.SavedFilter.dataset_id == dataset_id,
            models.SavedFilter.is_default == True
        ).update({"is_default": False})
    sf = models.SavedFilter(
        dataset_id=dataset_id,
        name=body.name,
        filter_model=body.filter_model,
        sort_model=body.sort_model,
        column_state=body.column_state,
        is_default=body.is_default,
        created_by=current_user.id,
    )
    db.add(sf)
    db.commit()
    db.refresh(sf)
    log_action(db, current_user.id, "CREATE_FILTER_VIEW", "DATASET", str(dataset_id), {"name": body.name})
    return sf


@router.patch("/{dataset_id}/filters/{filter_id}", response_model=schemas.SavedFilterOut)
def update_saved_filter(
    dataset_id: int,
    filter_id: int,
    body: schemas.SavedFilterUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=True))
):
    sf = db.query(models.SavedFilter).filter(
        models.SavedFilter.id == filter_id,
        models.SavedFilter.dataset_id == dataset_id
    ).first()
    if not sf:
        raise HTTPException(status_code=404, detail="Фильтр не найден")
    if body.name is not None: sf.name = body.name
    if body.filter_model is not None: sf.filter_model = body.filter_model
    if body.sort_model is not None: sf.sort_model = body.sort_model
    if body.column_state is not None: sf.column_state = body.column_state
    if body.is_default is not None:
        if body.is_default:
            db.query(models.SavedFilter).filter(
                models.SavedFilter.dataset_id == dataset_id,
                models.SavedFilter.is_default == True,
                models.SavedFilter.id != filter_id
            ).update({"is_default": False})
        sf.is_default = body.is_default
    db.commit()
    db.refresh(sf)
    return sf


@router.delete("/{dataset_id}/filters/{filter_id}", status_code=204)
def delete_saved_filter(
    dataset_id: int,
    filter_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=True))
):
    sf = db.query(models.SavedFilter).filter(
        models.SavedFilter.id == filter_id,
        models.SavedFilter.dataset_id == dataset_id
    ).first()
    if not sf:
        raise HTTPException(status_code=404, detail="Фильтр не найден")
    db.delete(sf)
    db.commit()
    return Response(status_code=204)


# ========================= СРЕЗЫ (SLICERS) =========================
@router.get("/{dataset_id}/slicers", response_model=List[schemas.SlicerOut])
def list_slicers(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=False))
):
    slicers = db.query(models.Slicer).filter(
        models.Slicer.dataset_id == dataset_id
    ).order_by(models.Slicer.created_at).all()
    return slicers


@router.post("/{dataset_id}/slicers", response_model=schemas.SlicerOut, status_code=201)
def create_slicer(
    dataset_id: int,
    body: schemas.SlicerCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=True))
):
    sl = models.Slicer(
        dataset_id=dataset_id,
        column_id=body.column_id,
        title=body.title,
        position=body.position,
        items=body.items,
        created_by=current_user.id,
    )
    db.add(sl)
    db.commit()
    db.refresh(sl)
    return sl


@router.patch("/{dataset_id}/slicers/{slicer_id}", response_model=schemas.SlicerOut)
def update_slicer(
    dataset_id: int,
    slicer_id: int,
    body: schemas.SlicerUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=True))
):
    sl = db.query(models.Slicer).filter(
        models.Slicer.id == slicer_id,
        models.Slicer.dataset_id == dataset_id
    ).first()
    if not sl:
        raise HTTPException(status_code=404, detail="Срез не найден")
    if body.title is not None: sl.title = body.title
    if body.position is not None: sl.position = body.position
    if body.items is not None: sl.items = body.items
    db.commit()
    db.refresh(sl)
    return sl


@router.delete("/{dataset_id}/slicers/{slicer_id}", status_code=204)
def delete_slicer(
    dataset_id: int,
    slicer_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=True))
):
    sl = db.query(models.Slicer).filter(
        models.Slicer.id == slicer_id,
        models.Slicer.dataset_id == dataset_id
    ).first()
    if not sl:
        raise HTTPException(status_code=404, detail="Срез не найден")
    db.delete(sl)
    db.commit()
    return Response(status_code=204)


# ========================= ИМЕНОВАННЫЕ ДИАПАЗОНЫ =========================
@router.get("/{dataset_id}/named-ranges", response_model=List[schemas.NamedRangeOut])
def list_named_ranges(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=False))
):
    ranges = db.query(models.NamedRange).filter(
        models.NamedRange.dataset_id == dataset_id
    ).order_by(models.NamedRange.name).all()
    return ranges


@router.post("/{dataset_id}/named-ranges", response_model=schemas.NamedRangeOut, status_code=201)
def create_named_range(
    dataset_id: int,
    body: schemas.NamedRangeCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=True))
):
    existing = db.query(models.NamedRange).filter(
        models.NamedRange.dataset_id == dataset_id,
        models.NamedRange.name == body.name
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Имя '{body.name}' уже используется")
    nr = models.NamedRange(
        dataset_id=dataset_id,
        name=body.name,
        sheet_id=body.sheet_id,
        start_col=body.start_col,
        start_row=body.start_row,
        end_col=body.end_col,
        end_row=body.end_row,
        formula=body.formula,
        created_by=current_user.id,
    )
    db.add(nr)
    db.commit()
    db.refresh(nr)
    return nr


@router.patch("/{dataset_id}/named-ranges/{range_id}", response_model=schemas.NamedRangeOut)
def update_named_range(
    dataset_id: int,
    range_id: int,
    body: schemas.NamedRangeUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=True))
):
    nr = db.query(models.NamedRange).filter(
        models.NamedRange.id == range_id,
        models.NamedRange.dataset_id == dataset_id
    ).first()
    if not nr:
        raise HTTPException(status_code=404, detail="Именованный диапазон не найден")
    if body.name is not None: nr.name = body.name
    if body.sheet_id is not None: nr.sheet_id = body.sheet_id
    if body.start_col is not None: nr.start_col = body.start_col
    if body.start_row is not None: nr.start_row = body.start_row
    if body.end_col is not None: nr.end_col = body.end_col
    if body.end_row is not None: nr.end_row = body.end_row
    if body.formula is not None: nr.formula = body.formula
    db.commit()
    db.refresh(nr)
    return nr


@router.delete("/{dataset_id}/named-ranges/{range_id}", status_code=204)
def delete_named_range(
    dataset_id: int,
    range_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    dataset: models.Dataset = Depends(dependencies.require_dataset_access(write=True))
):
    nr = db.query(models.NamedRange).filter(
        models.NamedRange.id == range_id,
        models.NamedRange.dataset_id == dataset_id
    ).first()
    if not nr:
        raise HTTPException(status_code=404, detail="Именованный диапазон не найден")
    db.delete(nr)
    db.commit()
    return Response(status_code=204)