"""add users.reset_code and reset_code_expires_at

Revision ID: e2a4c6f8b0d1
Revises: d1f4b6c8e3a5
Create Date: 2026-09-26 00:00:00.000000

Backs the staff forgot-password flow (see app/auth/service.py) - a 6-digit
verification code emailed via Gmail SMTP, not a URL token.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e2a4c6f8b0d1'
down_revision: Union[str, Sequence[str], None] = 'd1f4b6c8e3a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('reset_code', sa.String(length=6), nullable=True))
    op.add_column('users', sa.Column('reset_code_expires_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'reset_code_expires_at')
    op.drop_column('users', 'reset_code')
