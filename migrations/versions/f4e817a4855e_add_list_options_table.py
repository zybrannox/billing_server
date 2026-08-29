"""add list_options table

Revision ID: f4e817a4855e
Revises: 2334a98830b8
Create Date: 2026-08-29 00:00:00.000000

One generic table backs every admin-configurable dropdown (see
app/entities/list_option.py) - seeded here with Project Type's current
hardcoded options so the admin "System Setup" screen has something to
show and existing projects' values remain selectable, instead of the
picker starting out empty.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import table, column
from sqlalchemy.sql import func


# revision identifiers, used by Alembic.
revision: str = 'f4e817a4855e'
down_revision: Union[str, Sequence[str], None] = '2334a98830b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'list_options',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('value', sa.String(length=255), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('category', 'value', name='uq_list_option_category_value'),
    )
    op.create_index(op.f('ix_list_options_id'), 'list_options', ['id'])
    op.create_index(op.f('ix_list_options_category'), 'list_options', ['category'])

    list_options_t = table(
        'list_options',
        column('category', sa.String),
        column('value', sa.String),
        column('sort_order', sa.Integer),
        column('is_active', sa.Boolean),
    )
    op.bulk_insert(
        list_options_t,
        [
            {"category": "project_type", "value": "Flex", "sort_order": 1, "is_active": True},
            {"category": "project_type", "value": "Photo Frame", "sort_order": 2, "is_active": True},
            {"category": "project_type", "value": "Gift", "sort_order": 3, "is_active": True},
        ],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_list_options_category'), table_name='list_options')
    op.drop_index(op.f('ix_list_options_id'), table_name='list_options')
    op.drop_table('list_options')
