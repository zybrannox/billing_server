"""add issues, which employees report from the in-app helper

Revision ID: 7f3a91c2d4b6
Revises: 5c1e7a90d3b2
Create Date: 2026-11-06 00:00:00.000000

Purely additive: nothing existing changes, and downgrading only loses the issues.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7f3a91c2d4b6'
down_revision: Union[str, Sequence[str], None] = '5c1e7a90d3b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A development server creates missing tables by itself as it starts (see
    # app/main.py), so on a dev database this may already be there.
    if sa.inspect(op.get_bind()).has_table('issues'):
        return
    op.create_table(
        'issues',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('reported_by_id', sa.Integer(), nullable=True),
        sa.Column('reported_by', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('is_done', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('done_at', sa.DateTime(), nullable=True),
        sa.Column('done_by', sa.String(length=100), nullable=True),
        sa.Column('done_seen_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['reported_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_issues_id'), 'issues', ['id'], unique=False)
    op.create_index(op.f('ix_issues_reported_by_id'), 'issues', ['reported_by_id'], unique=False)
    op.create_index(op.f('ix_issues_is_done'), 'issues', ['is_done'], unique=False)


def downgrade() -> None:
    op.drop_table('issues')
