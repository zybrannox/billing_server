"""minimum charges per item type, starting with Flex

Revision ID: c7e9a1b3d5f7
Revises: a4c6e8b0d2f3
Create Date: 2026-11-05 00:00:00.000000

Adds a column, and gives Flex its starting minimums: Rs 150 up to 15 sq ft and
Rs 200 up to 20 sq ft. Both can be changed in System setup. Flex is added to the
catalog if it isn't there yet, with no default rate until one is set.
"""
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c7e9a1b3d5f7'
down_revision: Union[str, Sequence[str], None] = 'a4c6e8b0d2f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FLEX_MINIMUMS = [{"up_to_sq_ft": 15, "amount": 150}, {"up_to_sq_ft": 20, "amount": 200}]


def upgrade() -> None:
    op.add_column('list_options', sa.Column('min_charges', sa.JSON(), nullable=True))

    options = sa.table(
        'list_options',
        sa.column('id', sa.Integer),
        sa.column('category', sa.String),
        sa.column('value', sa.String),
        sa.column('sort_order', sa.Integer),
        sa.column('is_active', sa.Boolean),
        sa.column('created_at', sa.DateTime),
        sa.column('min_charges', sa.JSON),
    )
    bind = op.get_bind()
    is_flex = sa.and_(options.c.category == 'item_type', sa.func.lower(options.c.value) == 'flex')
    updated = bind.execute(sa.update(options).where(is_flex).values(min_charges=FLEX_MINIMUMS))
    if updated.rowcount == 0:
        last = bind.execute(
            sa.select(sa.func.max(options.c.sort_order)).where(options.c.category == 'item_type')
        ).scalar() or 0
        bind.execute(sa.insert(options).values(
            category='item_type', value='Flex', sort_order=last + 1, is_active=True,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None), min_charges=FLEX_MINIMUMS,
        ))


def downgrade() -> None:
    op.drop_column('list_options', 'min_charges')
