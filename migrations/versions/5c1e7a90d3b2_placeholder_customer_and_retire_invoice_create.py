"""placeholder customers, and creating invoices no longer needs access

Revision ID: 5c1e7a90d3b2
Revises: c7e9a1b3d5f7
Create Date: 2026-11-06 00:00:00.000000

The catch-all "UNKOWN NAME" customer is flagged so it stops being offered for
new projects. It stays a normal customer otherwise: older projects and invoices
still point at it.

Every employee can now create invoices, so "invoice.create" is dropped from
everyone's saved access. Downgrading doesn't give it back.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '5c1e7a90d3b2'
down_revision: Union[str, Sequence[str], None] = 'c7e9a1b3d5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('customers', sa.Column('is_placeholder', sa.Boolean(), nullable=False, server_default=sa.false()))
    bind = op.get_bind()

    customers = sa.table(
        'customers',
        sa.column('first_name', sa.String),
        sa.column('last_name', sa.String),
        sa.column('is_placeholder', sa.Boolean),
    )
    bind.execute(
        sa.update(customers)
        .where(
            sa.func.lower(sa.func.trim(customers.c.first_name)).in_(['unkown', 'unknown']),
            sa.func.lower(sa.func.trim(customers.c.last_name)) == 'name',
        )
        .values(is_placeholder=True)
    )

    users = sa.table('users', sa.column('id', sa.Integer), sa.column('permissions', sa.JSON))
    for user_id, permissions in bind.execute(sa.select(users.c.id, users.c.permissions)).all():
        if permissions and 'invoice.create' in permissions:
            bind.execute(
                sa.update(users)
                .where(users.c.id == user_id)
                .values(permissions=[p for p in permissions if p != 'invoice.create'])
            )


def downgrade() -> None:
    op.drop_column('customers', 'is_placeholder')
