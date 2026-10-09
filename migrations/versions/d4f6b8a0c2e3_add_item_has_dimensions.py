"""add has_dimensions to invoice_items and quotation_items

Revision ID: d4f6b8a0c2e3
Revises: b2d4f6a8c0e1
Create Date: 2026-10-09 00:00:00.000000

Lets a line be an "Others" item - billed by quantity (rate x pieces) rather
than by area. Every existing row is a measured line, hence the default.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4f6b8a0c2e3'
down_revision: Union[str, Sequence[str], None] = 'b2d4f6a8c0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    for table in ('invoice_items', 'quotation_items'):
        op.add_column(table, sa.Column('has_dimensions', sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    """Downgrade schema."""
    for table in ('quotation_items', 'invoice_items'):
        op.drop_column(table, 'has_dimensions')
