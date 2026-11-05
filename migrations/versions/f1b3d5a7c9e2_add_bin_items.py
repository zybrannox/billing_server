"""add the bin, which keeps deleted things for 14 days

Revision ID: f1b3d5a7c9e2
Revises: e1a3c5b7d9f2
Create Date: 2026-11-05 00:00:00.000000

Purely additive: nothing existing changes, and downgrading only loses what's
currently in the bin.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1b3d5a7c9e2'
down_revision: Union[str, Sequence[str], None] = 'e1a3c5b7d9f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'bin_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('item_type', sa.String(length=20), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=500), nullable=False),
        sa.Column('detail', sa.String(length=500), nullable=True),
        sa.Column('snapshot', sa.JSON(), nullable=False),
        sa.Column('size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('deleted_by', sa.String(length=100), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_bin_items_id'), 'bin_items', ['id'], unique=False)
    op.create_index(op.f('ix_bin_items_item_type'), 'bin_items', ['item_type'], unique=False)
    op.create_index(op.f('ix_bin_items_deleted_at'), 'bin_items', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_bin_items_expires_at'), 'bin_items', ['expires_at'], unique=False)


def downgrade() -> None:
    op.drop_table('bin_items')
