"""add ref, thread_id, row_index, col_index, parent_id, sub_unit_id to cell_comments

Revision ID: 005
Revises: 004
Create Date: 2026-06-07

"""
from alembic import op
import sqlalchemy as sa

revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('cell_comments', sa.Column('ref', sa.String(), nullable=True))
    op.add_column('cell_comments', sa.Column('thread_id', sa.String(), nullable=True))
    op.add_column('cell_comments', sa.Column('row_index', sa.Integer(), nullable=True))
    op.add_column('cell_comments', sa.Column('col_index', sa.Integer(), nullable=True))
    op.add_column('cell_comments', sa.Column('sub_unit_id', sa.String(), nullable=True, server_default='main'))
    op.add_column('cell_comments', sa.Column('parent_id', sa.Integer(),
                  sa.ForeignKey('cell_comments.id', ondelete='SET NULL'), nullable=True))
    op.alter_column('cell_comments', 'row_id', nullable=True)
    op.alter_column('cell_comments', 'column_id', nullable=True, server_default='')
    op.create_index('idx_cell_comments_thread', 'cell_comments', ['thread_id'])


def downgrade():
    op.drop_index('idx_cell_comments_thread', table_name='cell_comments')
    op.alter_column('cell_comments', 'column_id', nullable=False, server_default=None)
    op.alter_column('cell_comments', 'row_id', nullable=False)
    op.drop_column('cell_comments', 'parent_id')
    op.drop_column('cell_comments', 'sub_unit_id')
    op.drop_column('cell_comments', 'col_index')
    op.drop_column('cell_comments', 'row_index')
    op.drop_column('cell_comments', 'thread_id')
    op.drop_column('cell_comments', 'ref')
