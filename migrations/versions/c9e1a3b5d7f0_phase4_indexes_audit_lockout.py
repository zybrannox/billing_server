"""phase 4: filter indexes, audit_log, account lockout

Revision ID: c9e1a3b5d7f0
Revises: b8d0f2a4c6e8
Create Date: 2026-10-21 00:00:00.000000

* Indexes on the columns the list/dashboard queries filter by. They were
  full-table scans that only looked fast while the tables were small.
  (if_not_exists: a development database built by create_all already has them.)
* audit_log: append-only history of payments, cancellations and deletes. On
  Postgres a trigger rejects UPDATE/DELETE/TRUNCATE.
* failed_login_count / locked_until on users and client_accounts for the
  per-account lockout, and token_version for server-side session revocation.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c9e1a3b5d7f0'
down_revision: Union[str, Sequence[str], None] = 'b8d0f2a4c6e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEXES = [
    ('ix_invoices_v1_project_id', 'invoices_v1', ['project_id']),
    ('ix_invoices_v1_status', 'invoices_v1', ['status']),
    ('ix_quotations_customer_id', 'quotations', ['customer_id']),
    ('ix_quotations_status', 'quotations', ['status']),
    ('ix_projects_print_status', 'projects', ['print_status']),
    ('ix_projects_assigned_to', 'projects', ['assigned_to']),
    ('ix_job_requests_status', 'job_requests', ['status']),
]


def upgrade() -> None:
    for name, table, cols in INDEXES:
        op.create_index(name, table, cols, if_not_exists=True)

    for table in ('users', 'client_accounts'):
        op.add_column(table, sa.Column('token_version', sa.Integer(), nullable=False, server_default='0'))
        op.add_column(table, sa.Column('failed_login_count', sa.Integer(), nullable=False, server_default='0'))
        op.add_column(table, sa.Column('locked_until', sa.DateTime(), nullable=True))

    op.create_table(
        'audit_log',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('at', sa.DateTime(), nullable=False),
        sa.Column('actor', sa.String(100), nullable=False),
        sa.Column('action', sa.String(60), nullable=False),
        sa.Column('entity_type', sa.String(40), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=True),
        sa.Column('detail', sa.JSON(), nullable=True),
        if_not_exists=True,
    )
    op.create_index('ix_audit_log_at', 'audit_log', ['at'], if_not_exists=True)
    op.create_index('ix_audit_log_action', 'audit_log', ['action'], if_not_exists=True)
    op.create_index('ix_audit_log_entity', 'audit_log', ['entity_type', 'entity_id'], if_not_exists=True)

    if op.get_bind().dialect.name == 'postgresql':
        op.execute("""
            CREATE OR REPLACE FUNCTION audit_log_is_append_only() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'audit_log is append-only';
            END;
            $$ LANGUAGE plpgsql
        """)
        op.execute("""
            CREATE TRIGGER audit_log_no_update_delete
            BEFORE UPDATE OR DELETE ON audit_log
            FOR EACH ROW EXECUTE FUNCTION audit_log_is_append_only()
        """)
        op.execute("""
            CREATE TRIGGER audit_log_no_truncate
            BEFORE TRUNCATE ON audit_log
            FOR EACH STATEMENT EXECUTE FUNCTION audit_log_is_append_only()
        """)


def downgrade() -> None:
    if op.get_bind().dialect.name == 'postgresql':
        op.execute("DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit_log")
        op.execute("DROP TRIGGER IF EXISTS audit_log_no_update_delete ON audit_log")
        op.execute("DROP FUNCTION IF EXISTS audit_log_is_append_only()")
    op.drop_table('audit_log')
    for table in ('users', 'client_accounts'):
        op.drop_column(table, 'locked_until')
        op.drop_column(table, 'token_version')
        op.drop_column(table, 'failed_login_count')
    for name, table, _ in INDEXES:
        op.drop_index(name, table_name=table, if_exists=True)
