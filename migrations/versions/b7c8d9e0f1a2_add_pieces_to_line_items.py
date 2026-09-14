"""add pieces to invoice_items and quotation_items

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-09-12 00:00:00.000000

Lets one line bill for more than one identical piece (e.g. 10 identical
name boards at the same size/rate) without needing 10 separate rows - see
app/invoices/calculations.py's compute_line, which now multiplies `pieces`
into the stored total.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('invoice_items', sa.Column('pieces', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('quotation_items', sa.Column('pieces', sa.Integer(), nullable=False, server_default='1'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('quotation_items', 'pieces')
    op.drop_column('invoice_items', 'pieces')
