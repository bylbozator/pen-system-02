"""Initial schema with datasets

Revision ID: 001
Revises:
Create Date: 2026-04-06 15:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from passlib.context import CryptContext
import os

revision = '001'
down_revision = None
branch_labels = None
depends_on = None

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def upgrade() -> None:
    # ================== user_roles ==================
    op.create_table(
        'user_roles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('permissions', JSONB(), nullable=True),
        sa.Column('description', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_index(op.f('ix_user_roles_id'), 'user_roles', ['id'], unique=False)

    # ================== users ==================
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('hashed_password', sa.String(), nullable=False),
        sa.Column('last_name', sa.String(), nullable=True),
        sa.Column('first_name', sa.String(), nullable=True),
        sa.Column('middle_name', sa.String(), nullable=True),
        sa.Column('department', sa.String(), nullable=True),
        sa.Column('role_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['role_id'], ['user_roles.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('username')
    )
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)

    # ================== dataset_schemas ==================
    op.create_table(
        'dataset_schemas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('columns', JSONB(), nullable=False),
        sa.Column('header_row_1', JSONB(), nullable=True),
        sa.Column('header_row_2', JSONB(), nullable=True),
        sa.Column('header_row_2_colors', JSONB(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.text('now()')),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_dataset_schemas_id'), 'dataset_schemas', ['id'], unique=False)

    # ================== datasets ==================
    op.create_table(
        'datasets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=True),
        sa.Column('columns', JSONB(), nullable=False, server_default='[]'),
        sa.Column('header_row_1', JSONB(), nullable=True),
        sa.Column('header_row_2', JSONB(), nullable=True),
        sa.Column('header_row_2_colors', JSONB(), nullable=True),
        sa.Column('row_filter', JSONB(), nullable=True),
        sa.Column('unique_columns', JSONB(), nullable=True),
        sa.Column('default_sort_column', sa.String(), nullable=True),
        sa.Column('default_sort_order', sa.String(), nullable=True),
        sa.Column('schema_id', sa.Integer(), nullable=True),
        sa.Column('archived', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.text('now()')),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['schema_id'], ['dataset_schemas.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_datasets_id'), 'datasets', ['id'], unique=False)

    # ================== rows ==================
    op.create_table(
        'rows',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('dataset_id', sa.Integer(), nullable=True),
        sa.Column('data', JSONB(), nullable=False),
        sa.Column('formulas', JSONB(), nullable=True),
        sa.Column('row_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.text('now()')),
        sa.ForeignKeyConstraint(['dataset_id'], ['datasets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_rows_dataset_id', 'rows', ['dataset_id'])
    op.create_index('idx_rows_dataset_id_order', 'rows', ['dataset_id', 'row_order'])
    op.create_index('idx_rows_version', 'rows', ['version'])
    op.create_index('idx_rows_data_gin', 'rows', ['data'], postgresql_using='gin')
    op.create_index(op.f('ix_rows_id'), 'rows', ['id'], unique=False)

    # ================== row_history ==================
    op.create_table(
        'row_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('row_id', sa.Integer(), nullable=False),
        sa.Column('dataset_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('data', JSONB(), nullable=False),
        sa.Column('formulas', JSONB(), nullable=True),
        sa.Column('changed_by', sa.Integer(), nullable=True),
        sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('change_type', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['changed_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['dataset_id'], ['datasets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['row_id'], ['rows.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_row_history_row_id', 'row_history', ['row_id'])
    op.create_index('idx_row_history_dataset_id', 'row_history', ['dataset_id'])
    op.create_index('idx_row_history_version', 'row_history', ['row_id', 'version'])

    # ================== cell_history ==================
    op.create_table(
        'cell_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('dataset_id', sa.Integer(), nullable=False),
        sa.Column('row_id', sa.Integer(), nullable=False),
        sa.Column('column_id', sa.String(), nullable=False),
        sa.Column('old_value', sa.String(), nullable=True),
        sa.Column('new_value', sa.String(), nullable=True),
        sa.Column('changed_by', sa.Integer(), nullable=True),
        sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['changed_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['dataset_id'], ['datasets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['row_id'], ['rows.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_cell_history_dataset_row', 'cell_history', ['dataset_id', 'row_id'])
    op.create_index('idx_cell_history_column', 'cell_history', ['column_id'])
    op.create_index(op.f('ix_cell_history_id'), 'cell_history', ['id'], unique=False)

    # ================== cell_comments ==================
    op.create_table(
        'cell_comments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('dataset_id', sa.Integer(), nullable=False),
        sa.Column('row_id', sa.Integer(), nullable=False),
        sa.Column('column_id', sa.String(), nullable=False),
        sa.Column('comment', sa.String(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.text('now()')),
        sa.Column('resolved', sa.Boolean(), server_default='false'),
        sa.Column('resolved_by', sa.Integer(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['dataset_id'], ['datasets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['row_id'], ['rows.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_cell_comments_dataset', 'cell_comments', ['dataset_id'])
    op.create_index('idx_cell_comments_row', 'cell_comments', ['row_id'])
    op.create_index('idx_cell_comments_resolved', 'cell_comments', ['resolved'])
    op.create_index(op.f('ix_cell_comments_id'), 'cell_comments', ['id'], unique=False)

    # ================== user_action_logs ==================
    op.create_table(
        'user_action_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('entity_type', sa.String(), nullable=False),
        sa.Column('entity_id', sa.String(), nullable=True),
        sa.Column('details', JSONB(), nullable=True),
        sa.Column('ip_address', sa.String(), nullable=True),
        sa.Column('user_agent', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_logs_created_at', 'user_action_logs', ['created_at'])
    op.create_index(op.f('ix_user_action_logs_id'), 'user_action_logs', ['id'], unique=False)

    # ================== system_settings ==================
    op.create_table(
        'system_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('value', JSONB(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.text('now()')),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key')
    )
    op.create_index(op.f('ix_system_settings_id'), 'system_settings', ['id'], unique=False)

    # ================== SEED DATA ==================
    # Вставляем роли с актуальными правами
    op.execute("""
        INSERT INTO user_roles (name, permissions, description) VALUES
        ('снабжение', '{"can_create_datasets": true, "can_edit_own_sheets": true}', 'Отдел снабжения'),
        ('экономист', '{"can_edit_rows": true, "can_edit_fact_data": true}', 'Планово-экономический отдел'),
        ('руководитель', '{"can_view_all_datasets": true, "can_edit_all_datasets": true}', 'Руководство'),
        ('администратор', '{"full_access": true}', 'Полный доступ')
        ON CONFLICT (name) DO NOTHING;
    """)

    # Админский пользователь
    admin_password = os.getenv("ADMIN_PASSWORD", "admin")
    hashed = pwd_context.hash(admin_password)
    op.execute(f"""
        INSERT INTO users (username, email, hashed_password, role_id, is_active)
        VALUES ('admin', 'admin@example.com', '{hashed}',
            (SELECT id FROM user_roles WHERE name = 'администратор'), true)
        ON CONFLICT (username) DO UPDATE SET hashed_password = EXCLUDED.hashed_password;
    """)


def downgrade() -> None:
    op.drop_table('system_settings')
    op.drop_table('user_action_logs')
    op.drop_table('cell_comments')
    op.drop_table('cell_history')
    op.drop_table('row_history')
    op.drop_table('rows')
    op.drop_table('datasets')
    op.drop_table('dataset_schemas')
    op.drop_table('users')
    op.drop_table('user_roles')