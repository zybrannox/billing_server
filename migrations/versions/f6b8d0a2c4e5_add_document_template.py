"""add document_settings.template

Revision ID: f6b8d0a2c4e5
Revises: e5a7c9b1d3f4
Create Date: 2026-10-19 00:00:01.000000

Layout style for printed documents (classic / minimal / modern / compact),
chosen independently of the colour theme. Existing rows keep today's look.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6b8d0a2c4e5'
down_revision: Union[str, Sequence[str], None] = 'e5a7c9b1d3f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'document_settings',
        sa.Column('template', sa.String(length=20), nullable=False, server_default='classic'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('document_settings', 'template')
