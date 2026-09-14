"""add quotations tables

Revision ID: a1b2c3d4e5f6
Revises: f7a3b1c9e5d2
Create Date: 2026-09-12 00:00:00.000000

Adds the Quotation feature (see app/quotations/) - a pre-invoice estimate
for a customer before any project is committed to. Mirrors the
invoices_v1/invoice_items split (app/entities/invoice.py,
app/entities/invoice_item.py) but a quotation links to a customer directly
instead of a project, since the whole point is to price a job that isn't
one yet.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f7a3b1c9e5d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'quotations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('quotation_number', sa.String(length=50), nullable=True),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('project_type', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('subtotal', sa.Float(), nullable=False, server_default='0'),
        sa.Column('discount_amount', sa.Float(), nullable=False, server_default='0'),
        sa.Column('amount', sa.Float(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('valid_until', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('converted_project_id', sa.Integer(), nullable=True),
        sa.Column('converted_invoice_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id']),
        sa.ForeignKeyConstraint(['converted_project_id'], ['projects.id']),
        sa.ForeignKeyConstraint(['converted_invoice_id'], ['invoices_v1.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_quotations_id'), 'quotations', ['id'])
    op.create_index(op.f('ix_quotations_quotation_number'), 'quotations', ['quotation_number'], unique=True)

    op.create_table(
        'quotation_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('quotation_id', sa.Integer(), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('width', sa.Float(), nullable=False),
        sa.Column('height', sa.Float(), nullable=False),
        sa.Column('sq_ft', sa.Float(), nullable=False),
        sa.Column('rate', sa.Float(), nullable=False),
        sa.Column('total', sa.Float(), nullable=False),
        sa.Column('is_manual_total', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['quotation_id'], ['quotations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_quotation_items_id'), 'quotation_items', ['id'])
    op.create_index(op.f('ix_quotation_items_quotation_id'), 'quotation_items', ['quotation_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_quotation_items_quotation_id'), table_name='quotation_items')
    op.drop_index(op.f('ix_quotation_items_id'), table_name='quotation_items')
    op.drop_table('quotation_items')

    op.drop_index(op.f('ix_quotations_quotation_number'), table_name='quotations')
    op.drop_index(op.f('ix_quotations_id'), table_name='quotations')
    op.drop_table('quotations')
