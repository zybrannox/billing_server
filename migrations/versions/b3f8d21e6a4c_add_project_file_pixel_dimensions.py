"""add pixel_width/pixel_height to project_files

Revision ID: b3f8d21e6a4c
Revises: a2f6c9d1e4b7
Create Date: 2026-09-01 00:00:00.000000

project_files.width/height are a physical-size *estimate* in inches,
derived client-side from an assumed 96 DPI (see utils/appSupport.ts
getImageDimensions) - not something the file actually declares. That's
fine for a casual display elsewhere in the app, but the invoice-creation
screen needs a size it can trust for billing, and a guessed DPI isn't
one. These two new columns store the file's actual pixel dimensions
(img.naturalWidth/naturalHeight) - an assumption-free fact - so that
screen can show the user a real reference instead of a possibly-wrong
auto-filled size.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3f8d21e6a4c'
down_revision: Union[str, Sequence[str], None] = 'a2f6c9d1e4b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('project_files', sa.Column('pixel_width', sa.Integer(), nullable=True))
    op.add_column('project_files', sa.Column('pixel_height', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('project_files', 'pixel_height')
    op.drop_column('project_files', 'pixel_width')
