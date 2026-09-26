"""add client_accounts table

Revision ID: b8d2f4a6c1e3
Revises: a7c1e9f3b2d4
Create Date: 2026-09-16 00:00:00.000000

Backs the client portal's login (see app/client_auth) - a separate,
staff-invited-only auth boundary from staff's own users/UserRole, keyed 1:1
to an existing Customer row rather than a new role on the staff table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b8d2f4a6c1e3'
down_revision: Union[str, Sequence[str], None] = 'a7c1e9f3b2d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'client_accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('hashed_password', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('invite_token', sa.String(length=64), nullable=True),
        sa.Column('invite_token_expires_at', sa.DateTime(), nullable=True),
        sa.Column('invited_at', sa.DateTime(), nullable=True),
        sa.Column('invited_by', sa.String(length=100), nullable=True),
        sa.Column('activated_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_client_accounts_id'), 'client_accounts', ['id'], unique=False)
    op.create_index(op.f('ix_client_accounts_customer_id'), 'client_accounts', ['customer_id'], unique=True)
    op.create_index(op.f('ix_client_accounts_email'), 'client_accounts', ['email'], unique=True)
    op.create_index(op.f('ix_client_accounts_invite_token'), 'client_accounts', ['invite_token'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_client_accounts_invite_token'), table_name='client_accounts')
    op.drop_index(op.f('ix_client_accounts_email'), table_name='client_accounts')
    op.drop_index(op.f('ix_client_accounts_customer_id'), table_name='client_accounts')
    op.drop_index(op.f('ix_client_accounts_id'), table_name='client_accounts')
    op.drop_table('client_accounts')
