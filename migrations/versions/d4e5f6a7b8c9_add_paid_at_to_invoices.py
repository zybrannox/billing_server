"""add paid_at to invoices

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-14 00:00:00.000000

Tracks when an invoice actually became "paid", separately from
created_at. Revenue reporting (dashboard/repository.py's
revenue_this_month/get_revenue_trend) used to bucket by created_at, which
misattributes revenue whenever an invoice is paid well after it was
raised (an advance now, the balance weeks later) - the money would count
toward total_revenue immediately but never show up in "this month" or
the trend chart's current bucket. Nullable: existing paid invoices
predate this column, and reporting queries coalesce to created_at for
those.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('invoices_v1', sa.Column('paid_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('invoices_v1', 'paid_at')
