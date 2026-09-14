"""add unit to invoice_items and quotation_items

Revision ID: c3d4e5f6a7b8
Revises: b7c8d9e0f1a2
Create Date: 2026-09-14 00:00:00.000000

Lets a line item's width/height be entered in feet or inches instead of
always feet - a name board is more naturally "18in x 6in" than "1.5ft x
0.5ft". The rate stays per-square-foot regardless; see
app/invoices/calculations.py's compute_line, which converts sq inches ->
sq ft at 144 sq in/sq ft when unit="in". Existing rows default to "ft",
matching their original (only) unit.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b7c8d9e0f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('invoice_items', sa.Column('unit', sa.String(length=4), nullable=False, server_default='ft'))
    op.add_column('quotation_items', sa.Column('unit', sa.String(length=4), nullable=False, server_default='ft'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('quotation_items', 'unit')
    op.drop_column('invoice_items', 'unit')
