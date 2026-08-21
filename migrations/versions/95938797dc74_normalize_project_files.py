"""normalize project files into their own table

Revision ID: 95938797dc74
Revises: 4ab4898c6cd1
Create Date: 2026-08-21 00:00:00.000000

projects.file_paths (a JSON blob) required loading and scanning every
project's file list in Python just to find or update one file by name
(see mark_file_downloaded / delete_uploaded_file_endpoint in
app/project_files) - this replaces it with an indexed project_files table
keyed by the file's storage path.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import table, column, select
from sqlalchemy.sql import func


# revision identifiers, used by Alembic.
revision: str = '95938797dc74'
down_revision: Union[str, Sequence[str], None] = '4ab4898c6cd1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'project_files',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('path', sa.String(length=255), nullable=False),
        sa.Column('original_name', sa.String(length=500), nullable=True),
        sa.Column('width', sa.Float(), nullable=True),
        sa.Column('height', sa.Float(), nullable=True),
        sa.Column('downloaded', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=func.now()),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_project_files_id'), 'project_files', ['id'])
    op.create_index(op.f('ix_project_files_project_id'), 'project_files', ['project_id'])
    op.create_index(op.f('ix_project_files_path'), 'project_files', ['path'], unique=True)

    # Backfill from the JSON column before it's dropped. Done in plain SQL
    # (not the ORM) since this runs against whatever schema shape existed
    # at migration time, independent of the current model code.
    connection = op.get_bind()
    projects_t = table('projects', column('id', sa.Integer), column('file_paths', sa.JSON))
    rows = connection.execute(
        select(projects_t.c.id, projects_t.c.file_paths).where(
            projects_t.c.file_paths.isnot(None)
        )
    ).fetchall()

    project_files_t = table(
        'project_files',
        column('project_id', sa.Integer),
        column('path', sa.String),
        column('original_name', sa.String),
        column('width', sa.Float),
        column('height', sa.Float),
        column('downloaded', sa.Boolean),
    )
    for project_id, file_paths in rows:
        for entry in (file_paths or []):
            if not isinstance(entry, dict) or not entry.get('path'):
                continue
            connection.execute(
                project_files_t.insert().values(
                    project_id=project_id,
                    path=entry.get('path'),
                    original_name=entry.get('original_name'),
                    width=entry.get('width'),
                    height=entry.get('height'),
                    downloaded=bool(entry.get('downloaded') or False),
                )
            )

    op.drop_column('projects', 'file_paths')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('projects', sa.Column('file_paths', sa.JSON(), nullable=True))

    connection = op.get_bind()
    projects_t = table('projects', column('id', sa.Integer), column('file_paths', sa.JSON))
    project_files_t = table(
        'project_files',
        column('id', sa.Integer),
        column('project_id', sa.Integer),
        column('path', sa.String),
        column('original_name', sa.String),
        column('width', sa.Float),
        column('height', sa.Float),
        column('downloaded', sa.Boolean),
    )
    rows = connection.execute(
        select(
            project_files_t.c.project_id,
            project_files_t.c.path,
            project_files_t.c.original_name,
            project_files_t.c.width,
            project_files_t.c.height,
            project_files_t.c.downloaded,
        ).order_by(project_files_t.c.project_id, project_files_t.c.id)
    ).fetchall()

    by_project = {}
    for project_id, path, original_name, width, height, downloaded in rows:
        by_project.setdefault(project_id, []).append({
            "path": path,
            "original_name": original_name,
            "width": width,
            "height": height,
            "downloaded": downloaded,
        })

    for project_id, entries in by_project.items():
        connection.execute(
            projects_t.update()
            .where(projects_t.c.id == project_id)
            .values(file_paths=entries)
        )

    op.drop_index(op.f('ix_project_files_path'), table_name='project_files')
    op.drop_index(op.f('ix_project_files_project_id'), table_name='project_files')
    op.drop_index(op.f('ix_project_files_id'), table_name='project_files')
    op.drop_table('project_files')
