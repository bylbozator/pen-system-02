"""Add conditional_formatting column to datasets table

Revision ID: 003
Revises: 002
Create Date: 2026-06-03 22:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('datasets', sa.Column('conditional_formatting', JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('datasets', 'conditional_formatting')
