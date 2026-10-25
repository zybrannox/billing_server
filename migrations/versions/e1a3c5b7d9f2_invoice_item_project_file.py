"""link invoice items to the uploaded file they bill for

Revision ID: e1a3c5b7d9f2
Revises: d0f2b4a6c8e1
Create Date: 2026-10-25 00:00:00.000000

invoice_items.project_file_id lets an invoice's file gallery show only the
files that were actually invoiced. Nullable (hand-typed lines and invoices
raised earlier have none); deleting a file just clears the link.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e1a3c5b7d9f2'
down_revision: Union[str, Sequence[str], None] = 'd0f2b4a6c8e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('invoice_items', sa.Column('project_file_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_invoice_items_project_file', 'invoice_items', 'project_files', ['project_file_id'], ['id'], ondelete='SET NULL'
    )
    op.create_index('ix_invoice_items_project_file_id', 'invoice_items', ['project_file_id'])


def downgrade() -> None:
    op.drop_index('ix_invoice_items_project_file_id', table_name='invoice_items')
    op.drop_constraint('fk_invoice_items_project_file', 'invoice_items', type_='foreignkey')
    op.drop_column('invoice_items', 'project_file_id')
