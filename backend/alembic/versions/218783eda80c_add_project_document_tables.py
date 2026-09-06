"""add_project_document_tables

Revision ID: 218783eda80c
Revises: c3751fc92e5b
Create Date: 2026-08-19 03:18:35.478873

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '218783eda80c'
down_revision: Union[str, Sequence[str], None] = 'c3751fc92e5b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create the new tables
    op.create_table('epics',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('epic_id', sa.String(length=50), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=50), nullable=True),
    sa.Column('source_type', sa.String(length=50), nullable=True),
    sa.Column('source_reference', sa.String(length=255), nullable=True),
    sa.Column('source_text', sa.Text(), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table('features',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('epic_id', sa.String(length=50), nullable=True),
    sa.Column('feature_id', sa.String(length=50), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=50), nullable=True),
    sa.Column('source_type', sa.String(length=50), nullable=True),
    sa.Column('source_reference', sa.String(length=255), nullable=True),
    sa.Column('source_text', sa.Text(), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table('user_stories',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('feature_id', sa.String(length=50), nullable=True),
    sa.Column('story_id', sa.String(length=50), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('linked_requirement_ids', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=50), nullable=True),
    sa.Column('source_type', sa.String(length=50), nullable=True),
    sa.Column('source_reference', sa.String(length=255), nullable=True),
    sa.Column('source_text', sa.Text(), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table('acceptance_criteria',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('story_id', sa.String(length=50), nullable=True),
    sa.Column('ac_id', sa.String(length=50), nullable=False),
    sa.Column('statement', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=True),
    sa.Column('source_type', sa.String(length=50), nullable=True),
    sa.Column('source_reference', sa.String(length=255), nullable=True),
    sa.Column('source_text', sa.Text(), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table('project_agent_states',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('current_state', sa.String(length=100), nullable=True),
    sa.Column('document', sa.Text(), nullable=True),
    sa.Column('messages', sa.Text(), nullable=True),
    sa.Column('memory', sa.Text(), nullable=True),
    sa.Column('missing_info', sa.Text(), nullable=True),
    sa.Column('validation_attempts', sa.Integer(), nullable=True),
    sa.Column('last_reviewer_comments', sa.Text(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('project_id')
    )
    
    op.create_table('version_snapshots',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('version_num', sa.Integer(), nullable=True),
    sa.Column('document', sa.Text(), nullable=False),
    sa.Column('reviewer_comments', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    
    # 2. Add stage column to human_reviews using batch mode
    with op.batch_alter_table('human_reviews') as batch_op:
        batch_op.add_column(sa.Column('stage', sa.String(length=50), nullable=True))

    # 3. Add columns to development_execution_logs using batch mode
    with op.batch_alter_table('development_execution_logs') as batch_op:
        batch_op.add_column(sa.Column('task_id', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('files_generated', sa.Text(), nullable=True))

    # 4. Add columns and foreign key to development_versions using batch mode
    with op.batch_alter_table('development_versions') as batch_op:
        batch_op.add_column(sa.Column('parent_version_id', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('changed_files', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('reason_for_revision', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('review_comments', sa.Text(), nullable=True))
        batch_op.create_foreign_key('fk_dev_versions_parent', 'development_versions', ['parent_version_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('development_versions') as batch_op:
        batch_op.drop_constraint('fk_dev_versions_parent', type_='foreignkey')
        batch_op.drop_column('review_comments')
        batch_op.drop_column('reason_for_revision')
        batch_op.drop_column('changed_files')
        batch_op.drop_column('parent_version_id')

    with op.batch_alter_table('development_execution_logs') as batch_op:
        batch_op.drop_column('files_generated')
        batch_op.drop_column('task_id')

    with op.batch_alter_table('human_reviews') as batch_op:
        batch_op.drop_column('stage')

    op.drop_table('version_snapshots')
    op.drop_table('project_agent_states')
    op.drop_table('acceptance_criteria')
    op.drop_table('user_stories')
    op.drop_table('features')
    op.drop_table('epics')
