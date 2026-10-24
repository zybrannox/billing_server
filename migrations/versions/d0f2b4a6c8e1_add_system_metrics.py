"""add system_metrics (System Health history)

Revision ID: d0f2b4a6c8e1
Revises: c9e1a3b5d7f0
Create Date: 2026-10-24 00:00:00.000000

One row a minute (7 days kept, purged by the same job) so a lag spike can be
explained after the fact. Additive only - nothing existing is altered.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd0f2b4a6c8e1'
down_revision: Union[str, Sequence[str], None] = 'c9e1a3b5d7f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'system_metrics',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('at', sa.DateTime(), nullable=False),
        sa.Column('memory_available_pct', sa.Float(), nullable=False),
        sa.Column('swap_used_mb', sa.Float(), nullable=False),
        sa.Column('load_per_core', sa.Float(), nullable=False),
        sa.Column('disk_free_pct', sa.Float(), nullable=False),
        sa.Column('app_memory_mb', sa.Float(), nullable=False),
        sa.Column('db_connections_in_use', sa.Integer(), nullable=True),
        sa.Column('requests', sa.Integer(), nullable=False),
        sa.Column('errors', sa.Integer(), nullable=False),
        sa.Column('p95_ms', sa.Float(), nullable=True),
        if_not_exists=True,
    )
    op.create_index('ix_system_metrics_at', 'system_metrics', ['at'], if_not_exists=True)


def downgrade() -> None:
    op.drop_table('system_metrics')
