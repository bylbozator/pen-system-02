# backend/app/schemas.py

from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict
from typing import Any, Dict, List, Optional
from datetime import datetime
import uuid


# ======================== ПОЛЬЗОВАТЕЛИ И РОЛИ ========================
class UserBase(BaseModel):
    username: str
    email: EmailStr
    last_name: Optional[str] = None
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    department: Optional[str] = None


class UserCreate(UserBase):
    password: str
    role_id: int

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        from app.auth import validate_password_strength
        validate_password_strength(v)
        return v


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    last_name: Optional[str] = None
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    department: Optional[str] = None
    role_id: Optional[int] = None
    is_active: Optional[bool] = None

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            from app.auth import validate_password_strength
            validate_password_strength(v)
        return v


class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role_id: int
    role_name: Optional[str] = None
    is_active: bool
    last_login: Optional[datetime] = None
    created_at: datetime


class RoleCreate(BaseModel):
    name: str
    permissions: Dict[str, bool] = {}
    description: Optional[str] = None


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    permissions: Optional[Dict[str, bool]] = None
    description: Optional[str] = None


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    permissions: Dict[str, bool]
    description: Optional[str]


class Token(BaseModel):
    access_token: str
    token_type: str


class LoginRequest(BaseModel):
    username: str
    password: str


# ======================== ВАЛИДАЦИЯ ========================
class ValidationRule(BaseModel):
    type: str = "list"  # 'list', 'number', 'text_length', 'custom'
    allow_blank: bool = True
    show_dropdown: bool = True
    items: List[str] = []
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    formula: Optional[str] = None
    help_text: Optional[str] = None


# ======================== КОЛОНКИ ========================
class ColumnDef(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    header: str
    type: str
    editableBy: List[str] = []
    colorGroup: Optional[str] = None
    validation: Optional[ValidationRule] = None

    @field_validator('type')
    @classmethod
    def validate_type(cls, v: str) -> str:
        allowed = {'string', 'number', 'date'}
        if v not in allowed:
            raise ValueError(f"type must be one of: {', '.join(sorted(allowed))}")
        return v


# ======================== СХЕМЫ ДАТАСЕТОВ (опционально) ========================
class DatasetSchemaCreate(BaseModel):
    name: str
    columns: List[ColumnDef]
    header_row_1: Optional[Dict[str, Any]] = None
    header_row_2: Optional[Dict[str, Any]] = None
    header_row_2_colors: Optional[Dict[str, Any]] = None


class DatasetSchemaUpdate(BaseModel):
    name: Optional[str] = None
    columns: Optional[List[ColumnDef]] = None
    header_row_1: Optional[Dict[str, Any]] = None
    header_row_2: Optional[Dict[str, Any]] = None
    header_row_2_colors: Optional[Dict[str, Any]] = None


class DatasetSchemaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    columns: List[ColumnDef]
    header_row_1: Optional[Dict[str, Any]]
    header_row_2: Optional[Dict[str, Any]]
    header_row_2_colors: Optional[Dict[str, Any]]
    created_by: Optional[int]
    created_at: datetime
    updated_at: Optional[datetime]


# ======================== ДАТАСЕТЫ (бывшие листы) ========================
class ListDef(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Лист1"
    order: int = 0
    frozen_rows: int = 0
    frozen_columns: int = 0
    merged_cells: List[Dict[str, Any]] = []
    column_widths: Optional[Dict[str, float]] = None
    row_heights: Optional[Dict[str, float]] = None
    hidden_columns: List[str] = []
    hidden_rows: List[int] = []
    group_rows: List[Dict[str, Any]] = []
    group_columns: List[Dict[str, Any]] = []


class DatasetCreate(BaseModel):
    name: str
    schema_id: Optional[int] = None          # если создаётся на основе схемы
    row_filter: Optional[Dict[str, Any]] = None
    default_sort_column: Optional[str] = None
    default_sort_order: Optional[str] = "asc"
    unique_columns: Optional[List[str]] = None
    sub_sheets: Optional[List[ListDef]] = None

    @field_validator('default_sort_order')
    @classmethod
    def validate_sort_order(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ['asc', 'desc']:
            raise ValueError('default_sort_order must be "asc" or "desc"')
        return v


class DatasetUpdate(BaseModel):
    name: Optional[str] = None
    row_filter: Optional[Dict[str, Any]] = None
    unique_columns: Optional[List[str]] = None
    default_sort_column: Optional[str] = None
    default_sort_order: Optional[str] = None
    sub_sheets: Optional[List[ListDef]] = None
    styles: Optional[Dict[str, Any]] = None
    # Колонки можно редактировать только администратором через специальный эндпоинт,
    # поэтому здесь их не меняем, но если нужно, можно добавить columns: Optional[List[ColumnDef]]


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    owner_id: int
    owner_name: Optional[str] = None
    columns: List[ColumnDef]
    header_row_1: Optional[Dict[str, Any]] = None
    header_row_2: Optional[Dict[str, Any]] = None
    header_row_2_colors: Optional[Dict[str, Any]] = None
    row_filter: Optional[Dict[str, Any]] = None
    unique_columns: Optional[List[str]] = None
    default_sort_column: Optional[str] = None
    default_sort_order: Optional[str] = None
    schema_id: Optional[int] = None
    sub_sheets: Optional[List[ListDef]] = None
    styles: Optional[Dict[str, Any]] = None
    archived: bool
    created_at: datetime
    updated_at: Optional[datetime]


class DatasetsListResponse(BaseModel):
    items: List[DatasetOut]
    total: int
    skip: int
    limit: int


# ======================== СИСТЕМНЫЕ НАСТРОЙКИ ========================
class SystemSettingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    value: Any
    description: Optional[str] = None
    updated_by: Optional[int] = None
    updated_at: Optional[datetime] = None


class SystemSettingUpdate(BaseModel):
    value: Any
    description: Optional[str] = None


# ======================== СОХРАНЁННЫЕ ФИЛЬТРЫ ========================
class SavedFilterCreate(BaseModel):
    dataset_id: int
    name: str
    filter_model: Dict[str, Any] = {}
    sort_model: List[Dict[str, Any]] = []
    column_state: Optional[Dict[str, Any]] = None
    is_default: bool = False


class SavedFilterUpdate(BaseModel):
    name: Optional[str] = None
    filter_model: Optional[Dict[str, Any]] = None
    sort_model: Optional[List[Dict[str, Any]]] = None
    column_state: Optional[Dict[str, Any]] = None
    is_default: Optional[bool] = None


class SavedFilterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_id: int
    name: str
    filter_model: Dict[str, Any]
    sort_model: Optional[List[Dict[str, Any]]]
    column_state: Optional[Dict[str, Any]]
    is_default: bool
    created_by: Optional[int]
    created_at: datetime
    updated_at: Optional[datetime]


# ======================== СРЕЗЫ (SLICERS) ========================
class SlicerCreate(BaseModel):
    dataset_id: int
    column_id: str
    title: Optional[str] = None
    position: Optional[Dict[str, Any]] = None
    items: Optional[List[str]] = None


class SlicerUpdate(BaseModel):
    title: Optional[str] = None
    position: Optional[Dict[str, Any]] = None
    items: Optional[List[str]] = None


class SlicerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_id: int
    column_id: str
    title: Optional[str]
    position: Optional[Dict[str, Any]]
    items: Optional[List[str]]
    created_by: Optional[int]
    created_at: datetime


# ======================== ИМЕНОВАННЫЕ ДИАПАЗОНЫ ========================
class NamedRangeCreate(BaseModel):
    dataset_id: int
    name: str
    sheet_id: str = "main"
    start_col: str
    start_row: int
    end_col: Optional[str] = None
    end_row: Optional[int] = None
    formula: Optional[str] = None


class NamedRangeUpdate(BaseModel):
    name: Optional[str] = None
    sheet_id: Optional[str] = None
    start_col: Optional[str] = None
    start_row: Optional[int] = None
    end_col: Optional[str] = None
    end_row: Optional[int] = None
    formula: Optional[str] = None


class NamedRangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_id: int
    name: str
    sheet_id: str
    start_col: str
    start_row: int
    end_col: Optional[str]
    end_row: Optional[int]
    formula: Optional[str]
    created_by: Optional[int]
    created_at: datetime


# ======================== СТАТИСТИКА И АУДИТ ========================
class AdminStats(BaseModel):
    total_users: int
    active_users: int
    total_datasets: int
    archived_datasets: int
    total_rows: int
    total_comments: int


class AuditLogEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: Optional[int] = None
    username: Optional[str] = None
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: datetime


class AuditLogResponse(BaseModel):
    items: List[AuditLogEntry]
    total: int
    skip: int
    limit: int


# ======================== СТРОКИ ========================
class RowCreate(BaseModel):
    data: Dict[str, Any]
    formulas: Optional[Dict[str, str]] = None
    cell_styles: Optional[Dict[str, Any]] = None
    row_order: int = 0
    sheet_id: str = "main"


class RowUpdate(BaseModel):
    data: Dict[str, Any]
    formulas: Optional[Dict[str, str]] = None
    cell_styles: Optional[Dict[str, Any]] = None
    version: int
    sheet_id: Optional[str] = None
    row_order: Optional[int] = None


class RowBatchUpdate(BaseModel):
    id: int
    data: Dict[str, Any]
    formulas: Optional[Dict[str, str]] = None
    cell_styles: Optional[Dict[str, Any]] = None
    version: int
    sheet_id: Optional[str] = None
    row_order: Optional[int] = None


class CellUpdate(BaseModel):
    value: str
    formula: Optional[str] = None
    expected_version: Optional[int] = None  # для оптимистичной блокировки
    metadata: Optional[Dict[str, Any]] = None  # метаданные ячейки (_numberFormats, _dropdowns, и т.д.)


class DatasetColumnsUpdate(BaseModel):
    columns: List[ColumnDef]

class RowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_id: int
    sheet_id: str
    data: Dict[str, Any]
    formulas: Optional[Dict[str, str]]
    cell_styles: Optional[Dict[str, Any]]
    row_order: int
    version: int
    updated_at: Optional[datetime]


# ======================== ИСТОРИЯ ЯЧЕЙКИ ========================
class CellHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_id: int
    row_id: int
    column_id: str
    old_value: Optional[str]
    new_value: Optional[str]
    changed_by: Optional[int]
    changed_at: datetime


# ======================== КОММЕНТАРИИ ========================
class CellCommentCreate(BaseModel):
    comment: str
    column_id: str = ""
    row_id: Optional[int] = None

    # Univer-совместимые поля
    ref: Optional[str] = None
    thread_id: Optional[str] = None
    row_index: Optional[int] = None
    col_index: Optional[int] = None
    parent_id: Optional[int] = None
    sub_unit_id: Optional[str] = "main"


class CellCommentUpdate(BaseModel):
    comment: Optional[str] = None
    resolved: Optional[bool] = None

    # Univer-совместимые поля
    ref: Optional[str] = None
    thread_id: Optional[str] = None
    row_index: Optional[int] = None
    col_index: Optional[int] = None
    sub_unit_id: Optional[str] = None


class CellCommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_id: int
    row_id: Optional[int] = None
    column_id: str = ""
    comment: str
    created_by: int
    created_by_name: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    resolved: bool = False
    resolved_by: Optional[int] = None
    resolved_at: Optional[datetime] = None

    # Univer-совместимые поля
    ref: Optional[str] = None
    thread_id: Optional[str] = None
    row_index: Optional[int] = None
    col_index: Optional[int] = None
    parent_id: Optional[int] = None
    sub_unit_id: Optional[str] = "main"


class CellStylesUpdate(BaseModel):
    cell_styles: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = None  # _numberFormats, _dropdowns и т.д. — сохраняется в row.data