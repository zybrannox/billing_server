"""change_date_to_datetime

Revision ID: 22bf50400ead
Revises: e792fb0de646
Create Date: 2026-02-01 20:35:00.496960

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '22bf50400ead'
down_revision: Union[str, Sequence[str], None] = 'e792fb0de646'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Change start_date and delivery_date from Date to DateTime
    op.alter_column('projects', 'start_date',
                    type_=sa.DateTime(),
                    existing_type=sa.Date(),
                    nullable=True)
    op.alter_column('projects', 'delivery_date',
                    type_=sa.DateTime(),
                    existing_type=sa.Date(),
                    nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    # Revert DateTime back to Date
    op.alter_column('projects', 'start_date',
                    type_=sa.Date(),
                    existing_type=sa.DateTime(),
                    nullable=True)
    op.alter_column('projects', 'delivery_date',
                    type_=sa.Date(),
                    existing_type=sa.DateTime(),
                    nullable=True)
