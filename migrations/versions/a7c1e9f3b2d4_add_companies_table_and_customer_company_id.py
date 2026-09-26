"""add companies table and customer.company_id

Revision ID: a7c1e9f3b2d4
Revises: e5f6a7b8c9d0
Create Date: 2026-09-15 00:00:00.000000

Backs the Companies module (see app/companies) - B2B company accounts
with shared billing terms, linked via a nullable customers.company_id FK.
Deliberately no new Contact entity - a "contact" is just a Customer row
optionally linked to a Company, so Invoice/Project/Quotation's existing
customer_id FKs are untouched.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7c1e9f3b2d4'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'companies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('billing_email', sa.String(length=255), nullable=True),
        sa.Column('phone', sa.String(length=15), nullable=True),
        sa.Column('billing_address', sa.Text(), nullable=True),
        sa.Column('payment_terms_days', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('credit_limit', sa.Float(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_companies_id'), 'companies', ['id'], unique=False)
    op.create_index(op.f('ix_companies_name'), 'companies', ['name'], unique=False)

    op.add_column('customers', sa.Column('company_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_customers_company_id'), 'customers', ['company_id'], unique=False)
    op.create_foreign_key(
        'fk_customers_company_id_companies',
        'customers', 'companies',
        ['company_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_customers_company_id_companies', 'customers', type_='foreignkey')
    op.drop_index(op.f('ix_customers_company_id'), table_name='customers')
    op.drop_column('customers', 'company_id')

    op.drop_index(op.f('ix_companies_name'), table_name='companies')
    op.drop_index(op.f('ix_companies_id'), table_name='companies')
    op.drop_table('companies')
