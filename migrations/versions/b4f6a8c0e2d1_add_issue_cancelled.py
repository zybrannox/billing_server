"""let admins cancel an issue, as distinct from solving it

Revision ID: b4f6a8c0e2d1
Revises: 9d2e4b6a8c01
Create Date: 2026-11-07 00:00:00.000000

Purely additive: existing issues stay as they are. Downgrading puts cancelled
issues back to open, since that's all the older code can show.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b4f6a8c0e2d1'
down_revision: Union[str, Sequence[str], None] = '9d2e4b6a8c01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('issues', sa.Column('cancelled_at', sa.DateTime(), nullable=True))
    op.add_column('issues', sa.Column('cancelled_by', sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column('issues', 'cancelled_by')
    op.drop_column('issues', 'cancelled_at')
