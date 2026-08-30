"""add_testing_agent_tables

Revision ID: d481f9a01e23
Revises: c3751fc92e5b
Create Date: 2026-08-29 15:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd481f9a01e23'
down_revision: Union[str, Sequence[str], None] = 'c3751fc92e5b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('test_cases',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('version_id', sa.String(length=36), nullable=True),
        sa.Column('module', sa.String(length=150), nullable=False),
        sa.Column('test_type', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('duration', sa.Float(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('source_snippet', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.ForeignKeyConstraint(['version_id'], ['development_versions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('test_execution_reports',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('version_id', sa.String(length=36), nullable=True),
        sa.Column('total_unit', sa.Integer(), nullable=True),
        sa.Column('passed_unit', sa.Integer(), nullable=True),
        sa.Column('failed_unit', sa.Integer(), nullable=True),
        sa.Column('total_integration', sa.Integer(), nullable=True),
        sa.Column('passed_integration', sa.Integer(), nullable=True),
        sa.Column('failed_integration', sa.Integer(), nullable=True),
        sa.Column('overall_status', sa.String(length=20), nullable=True),
        sa.Column('report_pdf_path', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.ForeignKeyConstraint(['version_id'], ['development_versions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('test_execution_reports')
    op.drop_table('test_cases')
