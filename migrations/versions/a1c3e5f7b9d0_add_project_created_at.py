"""add projects.created_at

Revision ID: a1c3e5f7b9d0
Revises: f3b5d7a9c2e3
Create Date: 2026-09-29 00:00:00.000000

Backs the "Ongoing Activities" admin view rolling off projects older than 7
days once they're fully delivered (see app/projects/repository.py's
get_all_projects `view="ongoing"` filter) - the full, unfiltered history
stays on the new Project History page. `projects` never had a creation
timestamp before this. Existing rows are backfilled from `start_date`
(set at creation time on every project, so it's a real historical stand-in)
rather than "now" - backfilling to "now" would make every pre-existing
project look brand new and never roll off until 7 real days pass, which
defeats the point for exactly the old, already-delivered projects this
filter exists to hide. `server_default=now()` only kicks in for future
inserts that don't pass created_at explicitly.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1c3e5f7b9d0'
down_revision: Union[str, Sequence[str], None] = 'f3b5d7a9c2e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'projects',
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.execute(
        "UPDATE projects SET created_at = COALESCE(start_date, now()) "
        "WHERE created_at IS NULL"
    )
    op.alter_column('projects', 'created_at', nullable=False, server_default=sa.func.now())


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('projects', 'created_at')
