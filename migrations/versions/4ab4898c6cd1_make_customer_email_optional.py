"""make customer email optional

Revision ID: 4ab4898c6cd1
Revises: db0a7c30cc4a
Create Date: 2026-08-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4ab4898c6cd1'
down_revision: Union[str, Sequence[str], None] = 'db0a7c30cc4a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('customers', 'email',
               existing_type=sa.String(length=255),
               nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('customers', 'email',
               existing_type=sa.String(length=255),
               nullable=False)
