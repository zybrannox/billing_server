"""add rate to list_options

Revision ID: a2f6c9d1e4b7
Revises: c1d7e5a30f28
Create Date: 2026-08-30 00:00:00.000000

Backs the "Item Type" pricing catalog (see app/entities/list_option.py,
GenerateInvoice.tsx) - only meaningful for categories that price
themselves, null for everything else (e.g. "project_type").
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2f6c9d1e4b7'
down_revision: Union[str, Sequence[str], None] = 'c1d7e5a30f28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('list_options', sa.Column('rate', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('list_options', 'rate')
