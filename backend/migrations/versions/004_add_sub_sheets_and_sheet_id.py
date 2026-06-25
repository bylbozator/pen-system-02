"""add sub_sheets and sheet_id

Revision ID: 004
Revises: 003
Create Date: 2026-06-06

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('datasets', sa.Column('sub_sheets', JSONB,
                  default=lambda: [{"id": "main", "name": "Лист1", "order": 0}]))
    op.add_column('rows', sa.Column('sheet_id', sa.String(), nullable=False,
                  server_default='main'))
    op.create_index('idx_rows_sheet_id', 'rows', ['dataset_id', 'sheet_id'])


def downgrade():
    op.drop_index('idx_rows_sheet_id', table_name='rows')
    op.drop_column('rows', 'sheet_id')
    op.drop_column('datasets', 'sub_sheets')
