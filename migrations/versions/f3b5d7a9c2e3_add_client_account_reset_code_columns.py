"""add client_accounts.reset_code and reset_code_expires_at

Revision ID: f3b5d7a9c2e3
Revises: e2a4c6f8b0d1
Create Date: 2026-09-26 00:00:01.000000

Backs the client-portal forgot-password flow (see
app/client_auth/service.py) - same 6-digit verification-code pattern as
the staff side, kept separate from invite_token (first-time account setup
vs. an already-activated client resetting their password).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f3b5d7a9c2e3'
down_revision: Union[str, Sequence[str], None] = 'e2a4c6f8b0d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('client_accounts', sa.Column('reset_code', sa.String(length=6), nullable=True))
    op.add_column('client_accounts', sa.Column('reset_code_expires_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('client_accounts', 'reset_code_expires_at')
    op.drop_column('client_accounts', 'reset_code')
