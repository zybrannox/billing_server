"""add invoice discount and subtotal

Revision ID: c1d7e5a30f28
Revises: 8b3f2a91c4de
Create Date: 2026-08-29 00:00:00.000000

Splits the old single `amount` column into `subtotal` (raw sum of line
items) and `amount` (subtotal minus a manually-entered discount) - see
app/entities/invoice.py. Existing rows get subtotal = amount, discount = 0
so nothing changes for invoices generated before this feature existed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1d7e5a30f28'
down_revision: Union[str, Sequence[str], None] = '8b3f2a91c4de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'invoices_v1',
        sa.Column('discount_amount', sa.Float(), nullable=False, server_default='0'),
    )
    op.add_column(
        'invoices_v1',
        sa.Column('subtotal', sa.Float(), nullable=False, server_default='0'),
    )
    # Backfill: pre-existing invoices had no discount, so their subtotal
    # is just whatever `amount` already was.
    op.execute('UPDATE invoices_v1 SET subtotal = amount')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('invoices_v1', 'subtotal')
    op.drop_column('invoices_v1', 'discount_amount')
