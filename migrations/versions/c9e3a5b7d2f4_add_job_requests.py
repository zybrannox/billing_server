"""add job_requests and job_request_files tables

Revision ID: c9e3a5b7d2f4
Revises: b8d2f4a6c1e3
Create Date: 2026-09-16 00:00:01.000000

Backs client-submitted new work (see app/job_requests) - a client attaches
files via job_request_files before any Project exists; ProjectFile.project_id
stays NOT NULL and untouched. Staff converts a request into a real Project
(re-parenting its files by path, no copy) or rejects it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c9e3a5b7d2f4'
down_revision: Union[str, Sequence[str], None] = 'b8d2f4a6c1e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'job_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('reviewed_by', sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_job_requests_id'), 'job_requests', ['id'], unique=False)
    op.create_index(op.f('ix_job_requests_customer_id'), 'job_requests', ['customer_id'], unique=False)
    op.create_index(op.f('ix_job_requests_project_id'), 'job_requests', ['project_id'], unique=False)

    op.create_table(
        'job_request_files',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_request_id', sa.Integer(), nullable=False),
        sa.Column('path', sa.String(length=255), nullable=False),
        sa.Column('original_name', sa.String(length=500), nullable=True),
        sa.Column('width', sa.Float(), nullable=True),
        sa.Column('height', sa.Float(), nullable=True),
        sa.Column('pixel_width', sa.Integer(), nullable=True),
        sa.Column('pixel_height', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['job_request_id'], ['job_requests.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_job_request_files_id'), 'job_request_files', ['id'], unique=False)
    op.create_index(op.f('ix_job_request_files_job_request_id'), 'job_request_files', ['job_request_id'], unique=False)
    op.create_index(op.f('ix_job_request_files_path'), 'job_request_files', ['path'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_job_request_files_path'), table_name='job_request_files')
    op.drop_index(op.f('ix_job_request_files_job_request_id'), table_name='job_request_files')
    op.drop_index(op.f('ix_job_request_files_id'), table_name='job_request_files')
    op.drop_table('job_request_files')

    op.drop_index(op.f('ix_job_requests_project_id'), table_name='job_requests')
    op.drop_index(op.f('ix_job_requests_customer_id'), table_name='job_requests')
    op.drop_index(op.f('ix_job_requests_id'), table_name='job_requests')
    op.drop_table('job_requests')
