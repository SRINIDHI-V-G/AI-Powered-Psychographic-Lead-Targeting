"""003_phase_d_ocean_tables

Revision ID: c8f3a91e4d72
Revises: 29cdcf7af02d
Create Date: 2026-06-02 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c8f3a91e4d72'
down_revision: Union[str, None] = '29cdcf7af02d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_ocean_scores',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('openness', sa.Float(), nullable=False),
        sa.Column('conscientiousness', sa.Float(), nullable=False),
        sa.Column('extraversion', sa.Float(), nullable=False),
        sa.Column('agreeableness', sa.Float(), nullable=False),
        sa.Column('neuroticism', sa.Float(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='50.0'),
        sa.Column('scoring_method', sa.String(length=30), nullable=False, server_default='heuristic'),
        sa.Column('reasoning', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('raw_llm_response', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['discovered_users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', name='uq_user_ocean_score'),
    )
    op.create_index(
        op.f('ix_user_ocean_scores_user_id'),
        'user_ocean_scores',
        ['user_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_user_ocean_scores_user_id'), table_name='user_ocean_scores')
    op.drop_table('user_ocean_scores')
