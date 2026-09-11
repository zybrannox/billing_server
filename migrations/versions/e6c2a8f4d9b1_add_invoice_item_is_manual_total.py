"""add is_manual_total to invoice_items

Revision ID: e6c2a8f4d9b1
Revises: d4a9c7f1b2e3
Create Date: 2026-09-09 00:00:00.000000

Marks a line item whose Total was typed directly in the create form
(GenerateInvoice.tsx), with `rate` back-derived from it (rate = total ÷
area) rather than being what was actually entered. `rate` is still
required and still drives the stored total either way - this only tells
the invoice view whether to show it, since a solved-for number nobody
actually typed isn't a real rate to display.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6c2a8f4d9b1'
down_revision: Union[str, Sequence[str], None] = 'd4a9c7f1b2e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'invoice_items',
        sa.Column('is_manual_total', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('invoice_items', 'is_manual_total')
