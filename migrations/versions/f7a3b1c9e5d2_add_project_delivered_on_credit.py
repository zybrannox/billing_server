"""add delivered_on_credit to projects

Revision ID: f7a3b1c9e5d2
Revises: e6c2a8f4d9b1
Create Date: 2026-09-09 00:00:00.000000

Marks a delivery that was explicitly made while the invoice was still
unpaid (see DeliveryCheck.tsx's "Deliver on Credit" action) - a deliberate
business decision, not an oversight. Kept as its own flag rather than
inferred from invoice status, since the invoice can later be marked paid
(settling the credit) while this stays as the historical record of how
the delivery actually happened.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7a3b1c9e5d2'
down_revision: Union[str, Sequence[str], None] = 'e6c2a8f4d9b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'projects',
        sa.Column('delivered_on_credit', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('projects', 'delivered_on_credit')
