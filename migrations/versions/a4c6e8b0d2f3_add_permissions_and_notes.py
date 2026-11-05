"""per-employee access, and job notes

Revision ID: a4c6e8b0d2f3
Revises: f1b3d5a7c9e2
Create Date: 2026-11-05 00:00:00.000000

Everyone starts with no extra access: admins grant it per employee.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a4c6e8b0d2f3'
down_revision: Union[str, Sequence[str], None] = 'f1b3d5a7c9e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('permissions', sa.JSON(), nullable=False, server_default='[]'))
    # A development server creates missing tables by itself as it starts (see
    # app/main.py), so on a dev database this one may already be there.
    if sa.inspect(op.get_bind()).has_table('notes'):
        return
    op.create_table(
        'notes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=True),
        sa.Column('created_by', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('is_done', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('done_at', sa.DateTime(), nullable=True),
        sa.Column('done_by', sa.String(length=100), nullable=True),
        sa.Column('invoice_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices_v1.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_notes_id'), 'notes', ['id'], unique=False)
    op.create_index(op.f('ix_notes_customer_id'), 'notes', ['customer_id'], unique=False)
    op.create_index(op.f('ix_notes_is_done'), 'notes', ['is_done'], unique=False)
    op.create_index(op.f('ix_notes_invoice_id'), 'notes', ['invoice_id'], unique=False)


def downgrade() -> None:
    op.drop_table('notes')
    op.drop_column('users', 'permissions')
