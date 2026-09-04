"""add invoice advance payment fields

Revision ID: 8b3f2a91c4de
Revises: 67a3eef5b0d6
Create Date: 2026-08-29 00:00:00.000000

Manually-recorded advance payment on an invoice - no payment gateway
involved. See app/entities/invoice.py.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8b3f2a91c4de'
down_revision: Union[str, Sequence[str], None] = '67a3eef5b0d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'invoices_v1',
        sa.Column('advance_amount', sa.Float(), nullable=False, server_default='0'),
    )
    op.add_column('invoices_v1', sa.Column('payment_method', sa.String(length=30), nullable=True))
    op.add_column('invoices_v1', sa.Column('payment_reference', sa.String(length=100), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('invoices_v1', 'payment_reference')
    op.drop_column('invoices_v1', 'payment_method')
    op.drop_column('invoices_v1', 'advance_amount')
