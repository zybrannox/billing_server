"""add document_settings

Revision ID: e5a7c9b1d3f4
Revises: d4f6b8a0c2e3
Create Date: 2026-10-19 00:00:00.000000

Single-row table holding the shop's branding/theme for printed documents
(see app/entities/document_settings.py). The row itself is created lazily
on first read, so no data migration is needed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5a7c9b1d3f4'
down_revision: Union[str, Sequence[str], None] = 'd4f6b8a0c2e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'document_settings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('business_name', sa.String(length=120), nullable=False),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('phone', sa.String(length=40), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('website', sa.String(length=255), nullable=True),
        sa.Column('tax_id', sa.String(length=40), nullable=True),
        sa.Column('logo_path', sa.String(length=255), nullable=True),
        sa.Column('theme', sa.String(length=20), nullable=False),
        sa.Column('custom_color', sa.String(length=7), nullable=True),
        sa.Column('show_top_bar', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('show_payment_history', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('tax_label', sa.String(length=40), nullable=False),
        sa.Column('tax_note', sa.String(length=80), nullable=False),
        sa.Column('invoice_terms', sa.Text(), nullable=True),
        sa.Column('quotation_terms', sa.Text(), nullable=True),
        sa.Column('footer_message', sa.String(length=200), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('document_settings')
