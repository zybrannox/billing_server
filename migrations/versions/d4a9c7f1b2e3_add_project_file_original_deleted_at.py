"""add original_deleted_at to project_files

Revision ID: d4a9c7f1b2e3
Revises: b3f8d21e6a4c
Create Date: 2026-09-08 00:00:00.000000

Backs the weekly retention job (app/project_files/retention.py), which
permanently deletes the original file for storage on completed/delivered/
invoiced projects once it's 7+ days old, keeping only the thumbnail and
this row (path/original_name/dimensions) so the UI can still show what
the file was. Null means the original is still on disk.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4a9c7f1b2e3'
down_revision: Union[str, Sequence[str], None] = 'b3f8d21e6a4c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('project_files', sa.Column('original_deleted_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('project_files', 'original_deleted_at')
