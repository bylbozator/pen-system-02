# backend/app/models.py

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON, Index
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.database import Base


# ========== СХЕМЫ ДАТАСЕТОВ (ОПЦИОНАЛЬНО) ==========
class DatasetSchema(Base):
    __tablename__ = "dataset_schemas"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    columns = Column(JSONB, nullable=False)          # список колонок: id, header, type, editableBy, colorGroup
    header_row_1 = Column(JSONB, nullable=True)      # формулы итогов
    header_row_2 = Column(JSONB, nullable=True)      # текст групп
    header_row_2_colors = Column(JSONB, nullable=True)  # цвета групп
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# ========== ДАТАСЕТ (Аналог бывшего Sheet + Template) ==========
class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    columns = Column(JSONB, nullable=False, default=list)    # скопировано или сгенерировано при импорте
    header_row_1 = Column(JSONB, nullable=True)
    header_row_2 = Column(JSONB, nullable=True)
    header_row_2_colors = Column(JSONB, nullable=True)
    row_filter = Column(JSONB, nullable=True)
    unique_columns = Column(JSONB, nullable=True)
    default_sort_column = Column(String, nullable=True)
    default_sort_order = Column(String, nullable=True)
    schema_id = Column(Integer, ForeignKey("dataset_schemas.id"), nullable=True)  # ссылка на схему, если использовалась
    conditional_formatting = Column(JSONB, nullable=True, default=list)  # правила условного форматирования
    styles = Column(JSONB, nullable=True, default=dict)  # мапа стилей ячеек (IWorkbookData.styles)
    sub_sheets = Column(JSONB, default=lambda: [{"id": "main", "name": "Лист1", "order": 0}])
    archived = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    owner = relationship("User")
    schema = relationship("DatasetSchema")
    rows = relationship("Row", cascade="all, delete-orphan")
    comments = relationship("CellComment", cascade="all, delete-orphan")


# ========== ПОЛЬЗОВАТЕЛИ И РОЛИ ==========
class UserRole(Base):
    __tablename__ = "user_roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    permissions = Column(JSONB, default={})
    description = Column(String)

    users = relationship("User", back_populates="role")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    last_name = Column(String)
    first_name = Column(String)
    middle_name = Column(String)
    department = Column(String, nullable=True)
    role_id = Column(Integer, ForeignKey("user_roles.id"))
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime(timezone=True))
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    role = relationship("UserRole", back_populates="users")


# ========== СТРОКИ ==========
class Row(Base):
    __tablename__ = "rows"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"))
    sheet_id = Column(String, nullable=False, default="main", server_default="main")
    data = Column(JSONB, nullable=False, default=dict)
    formulas = Column(JSONB, default=dict)
    cell_styles = Column(JSONB, default=dict)
    row_order = Column(Integer, nullable=False, default=0)
    version = Column(Integer, nullable=False, default=1)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    dataset = relationship("Dataset", overlaps="rows")

    __table_args__ = (
        Index("idx_rows_dataset_id", "dataset_id"),
        Index("idx_rows_dataset_id_order", "dataset_id", "row_order"),
        Index("idx_rows_version", "version"),
        Index("idx_rows_data_gin", "data", postgresql_using="gin"),
        Index("idx_rows_sheet_id", "dataset_id", "sheet_id"),
    )


# ========== ИСТОРИЯ СТРОК ==========
class RowHistory(Base):
    __tablename__ = "row_history"

    id = Column(Integer, primary_key=True, index=True)
    row_id = Column(Integer, ForeignKey("rows.id", ondelete="CASCADE"), nullable=False)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, nullable=False)
    data = Column(JSONB, nullable=False)
    formulas = Column(JSONB, default={})
    changed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())
    change_type = Column(String, nullable=False)


# ========== ИСТОРИЯ ЯЧЕЕК ==========
class CellHistory(Base):
    __tablename__ = "cell_history"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    row_id = Column(Integer, ForeignKey("rows.id", ondelete="CASCADE"), nullable=False)
    column_id = Column(String, nullable=False)
    old_value = Column(String, nullable=True)
    new_value = Column(String, nullable=True)
    changed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_cell_history_dataset_row", "dataset_id", "row_id"),
        Index("idx_cell_history_column", "column_id"),
    )


# ========== КОММЕНТАРИИ К ЯЧЕЙКАМ ==========
class CellComment(Base):
    __tablename__ = "cell_comments"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    row_id = Column(Integer, ForeignKey("rows.id", ondelete="CASCADE"), nullable=True)
    column_id = Column(String, nullable=False)

    comment = Column(String, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    resolved = Column(Boolean, default=False)
    resolved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    # Univer-совместимые поля
    ref = Column(String, nullable=True, comment="cell reference like 'A1'")
    thread_id = Column(String, nullable=True, comment="thread grouping ID")
    row_index = Column(Integer, nullable=True, comment="0-based row index in sheet")
    col_index = Column(Integer, nullable=True, comment="0-based column index in sheet")
    parent_id = Column(Integer, ForeignKey("cell_comments.id", ondelete="SET NULL"), nullable=True)
    sub_unit_id = Column(String, nullable=True, default="main", comment="sheet ID")

    __table_args__ = (
        Index("idx_cell_comments_dataset", "dataset_id"),
        Index("idx_cell_comments_row", "row_id"),
        Index("idx_cell_comments_resolved", "resolved"),
        Index("idx_cell_comments_thread", "thread_id"),
    )

    parent = relationship("CellComment", remote_side=[id], backref="replies")


# ========== СОХРАНЁННЫЕ ФИЛЬТРЫ (FILTER VIEWS) ==========
class SavedFilter(Base):
    __tablename__ = "saved_filters"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    filter_model = Column(JSONB, nullable=False, default=dict)   # AG Grid filter model
    sort_model = Column(JSONB, nullable=True, default=list)      # multi-column sort model
    column_state = Column(JSONB, nullable=True)                   # visibility, width, order
    is_default = Column(Boolean, default=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# ========== СРЕЗЫ (SLICERS) ==========
class Slicer(Base):
    __tablename__ = "slicers"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    column_id = Column(String, nullable=False)
    title = Column(String, nullable=True)
    position = Column(JSONB, nullable=True)      # {x, y, width, height}
    items = Column(JSONB, nullable=True)          # selected items (null = all)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ========== ИМЕНОВАННЫЕ ДИАПАЗОНЫ ==========
class NamedRange(Base):
    __tablename__ = "named_ranges"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    sheet_id = Column(String, nullable=False, default="main")
    start_col = Column(String, nullable=False)
    start_row = Column(Integer, nullable=False)
    end_col = Column(String, nullable=True)
    end_row = Column(Integer, nullable=True)
    formula = Column(String, nullable=True)       # optional: could point to a formula
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_named_ranges_dataset", "dataset_id"),
    )


# ========== АУДИТ И НАСТРОЙКИ (БЕЗ ИЗМЕНЕНИЙ) ==========
class UserActionLog(Base):
    __tablename__ = "user_action_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    action = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String)
    details = Column(JSONB)
    ip_address = Column(String)
    user_agent = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_logs_created_at", "created_at"),
    )


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, nullable=False)
    value = Column(JSONB, nullable=False)
    description = Column(String)
    updated_by = Column(Integer, ForeignKey("users.id"))
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())