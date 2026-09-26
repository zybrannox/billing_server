"""add projects.notified_at and notified_by

Revision ID: d1f4b6c8e3a5
Revises: c9e3a5b7d2f4
Create Date: 2026-09-16 00:00:02.000000

Backs the staff-triggered "Notify Client (WhatsApp)" action - a "last
notified" fact (not idempotent-gated like delivered_at/design_completed_at),
since staff may re-notify. See app/projects/controller.py's /notify route.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd1f4b6c8e3a5'
down_revision: Union[str, Sequence[str], None] = 'c9e3a5b7d2f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('projects', sa.Column('notified_at', sa.DateTime(), nullable=True))
    op.add_column('projects', sa.Column('notified_by', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('projects', 'notified_by')
    op.drop_column('projects', 'notified_at')
