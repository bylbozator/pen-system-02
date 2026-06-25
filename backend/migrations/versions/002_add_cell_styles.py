"""Add cell_styles column to rows table

Revision ID: 002
Revises: 001
Create Date: 2026-05-21 22:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('rows', sa.Column('cell_styles', JSONB(), nullable=True))
    op.create_index('idx_rows_cell_styles_gin', 'rows', ['cell_styles'], postgresql_using='gin')


def downgrade() -> None:
    op.drop_index('idx_rows_cell_styles_gin')
    op.drop_column('rows', 'cell_styles')
