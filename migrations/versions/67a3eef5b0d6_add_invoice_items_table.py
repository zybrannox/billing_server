"""add invoice_items table

Revision ID: 67a3eef5b0d6
Revises: f4e817a4855e
Create Date: 2026-08-29 00:00:00.000000

Splits an invoice's single flat `amount` into per-line-item billing
(width x height => sq_ft, at a per-sq-ft rate) - see
app/entities/invoice_item.py. `invoices_v1.amount` is now the sum of its
items' totals, computed server-side at creation (app/invoices/repository.py)
rather than trusted from the client.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '67a3eef5b0d6'
down_revision: Union[str, Sequence[str], None] = 'f4e817a4855e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'invoice_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('invoice_id', sa.Integer(), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('width', sa.Float(), nullable=False),
        sa.Column('height', sa.Float(), nullable=False),
        sa.Column('sq_ft', sa.Float(), nullable=False),
        sa.Column('rate', sa.Float(), nullable=False),
        sa.Column('total', sa.Float(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices_v1.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_invoice_items_id'), 'invoice_items', ['id'])
    op.create_index(op.f('ix_invoice_items_invoice_id'), 'invoice_items', ['invoice_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_invoice_items_invoice_id'), table_name='invoice_items')
    op.drop_index(op.f('ix_invoice_items_id'), table_name='invoice_items')
    op.drop_table('invoice_items')
