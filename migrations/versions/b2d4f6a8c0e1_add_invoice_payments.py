"""add invoice_payments (payment history)

Revision ID: b2d4f6a8c0e1
Revises: a1c3e5f7b9d0
Create Date: 2026-10-02 00:00:00.000000

Per-invoice payment ledger backing partial payments (see
app/invoices/service.py's service_record_payment). Existing invoices with
an advance/settlement on record get one backfilled entry for that amount,
so their history already sums to what balance_due assumes was received.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2d4f6a8c0e1'
down_revision: Union[str, Sequence[str], None] = 'a1c3e5f7b9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'invoice_payments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('invoice_id', sa.Integer(), sa.ForeignKey('invoices_v1.id', ondelete='CASCADE'), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('payment_method', sa.String(length=30), nullable=True),
        sa.Column('payment_reference', sa.String(length=100), nullable=True),
        sa.Column('paid_at', sa.DateTime(), nullable=False),
        sa.Column('recorded_by', sa.String(length=50), nullable=True),
    )
    op.create_index('ix_invoice_payments_id', 'invoice_payments', ['id'])
    op.create_index('ix_invoice_payments_invoice_id', 'invoice_payments', ['invoice_id'])
    op.execute(
        "INSERT INTO invoice_payments (invoice_id, amount, payment_method, payment_reference, paid_at) "
        "SELECT id, advance_amount, payment_method, payment_reference, COALESCE(paid_at, created_at) "
        "FROM invoices_v1 WHERE advance_amount > 0"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_invoice_payments_invoice_id', table_name='invoice_payments')
    op.drop_index('ix_invoice_payments_id', table_name='invoice_payments')
    op.drop_table('invoice_payments')
