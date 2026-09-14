"""add shared_documents table

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-14 00:00:00.000000

Backs the "Share to WhatsApp" link feature (see app/shared_documents) -
a public, token-addressed pointer to a generated invoice/quotation PDF,
so it can be opened by a customer with no Zybrannox account.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'shared_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('document_type', sa.String(length=20), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('display_name', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('document_type', 'document_id', name='uq_shared_document_type_id'),
        sa.UniqueConstraint('token'),
    )
    op.create_index(op.f('ix_shared_documents_id'), 'shared_documents', ['id'], unique=False)
    op.create_index(op.f('ix_shared_documents_token'), 'shared_documents', ['token'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_shared_documents_token'), table_name='shared_documents')
    op.drop_index(op.f('ix_shared_documents_id'), table_name='shared_documents')
    op.drop_table('shared_documents')
