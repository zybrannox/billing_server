"""mark the hidden project behind a bill created on its own

Revision ID: 9d2e4b6a8c01
Revises: 7f3a91c2d4b6
Create Date: 2026-11-07 00:00:00.000000

Purely additive: every existing project stays visible. Only bills created from
now on are hidden from the project lists.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9d2e4b6a8c01'
down_revision: Union[str, Sequence[str], None] = '7f3a91c2d4b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('projects', sa.Column('bill_only', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('projects', 'bill_only')
