"""add document_settings.tagline

Revision ID: a7c9e1b3d5f6
Revises: f6b8d0a2c4e5
Create Date: 2026-10-19 00:00:02.000000

Brand slogan printed under the logo on documents. Existing rows get the
shop's current tagline.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7c9e1b3d5f6'
down_revision: Union[str, Sequence[str], None] = 'f6b8d0a2c4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'document_settings',
        sa.Column('tagline', sa.String(length=160), nullable=True, server_default='Printing & Signage Services'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('document_settings', 'tagline')
