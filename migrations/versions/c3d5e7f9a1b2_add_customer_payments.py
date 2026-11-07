"""customer payments: one sum from a customer, split across their invoices

Revision ID: c3d5e7f9a1b2
Revises: b4f6a8c0e2d1
Create Date: 2026-11-07 00:00:00.000000

Purely additive: a new table, and a nullable link on the existing payment
history. Every existing payment keeps working exactly as before.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d5e7f9a1b2'
down_revision: Union[str, Sequence[str], None] = 'b4f6a8c0e2d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    # A development database may already have the (empty) table: the app creates
    # missing tables on startup outside production. The link column never is.
    if not inspector.has_table('customer_payments'):
        _create_customer_payments()
    op.add_column('invoice_payments', sa.Column('customer_payment_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'invoice_payments_customer_payment_id_fkey', 'invoice_payments', 'customer_payments',
        ['customer_payment_id'], ['id'], ondelete='SET NULL',
    )
    op.create_index(op.f('ix_invoice_payments_customer_payment_id'), 'invoice_payments', ['customer_payment_id'])


def _create_customer_payments() -> None:
    op.create_table(
        'customer_payments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('payment_method', sa.String(length=30), nullable=False),
        sa.Column('payment_reference', sa.String(length=100), nullable=True),
        sa.Column('note', sa.String(length=500), nullable=True),
        sa.Column('received_at', sa.DateTime(), nullable=False),
        sa.Column('recorded_by', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index(op.f('ix_customer_payments_id'), 'customer_payments', ['id'])
    op.create_index(op.f('ix_customer_payments_customer_id'), 'customer_payments', ['customer_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_invoice_payments_customer_payment_id'), table_name='invoice_payments')
    op.drop_constraint('invoice_payments_customer_payment_id_fkey', 'invoice_payments', type_='foreignkey')
    op.drop_column('invoice_payments', 'customer_payment_id')
    op.drop_index(op.f('ix_customer_payments_customer_id'), table_name='customer_payments')
    op.drop_index(op.f('ix_customer_payments_id'), table_name='customer_payments')
    op.drop_table('customer_payments')
