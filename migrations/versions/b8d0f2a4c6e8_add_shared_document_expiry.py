"""add shared_documents.expires_at / revoked_at

Revision ID: b8d0f2a4c6e8
Revises: a7c9e1b3d5f6
Create Date: 2026-10-20 00:00:00.000000

Shared document links (the WhatsApp "view your invoice" URLs) used to work
forever. They now expire, and can be revoked. Existing links get 30 days from
their last refresh, so the oldest stop working immediately and the rest on
schedule.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b8d0f2a4c6e8'
down_revision: Union[str, Sequence[str], None] = 'a7c9e1b3d5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('shared_documents', sa.Column('expires_at', sa.DateTime(), nullable=True))
    op.add_column('shared_documents', sa.Column('revoked_at', sa.DateTime(), nullable=True))
    op.execute("UPDATE shared_documents SET expires_at = updated_at + interval '30 days'")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('shared_documents', 'revoked_at')
    op.drop_column('shared_documents', 'expires_at')
