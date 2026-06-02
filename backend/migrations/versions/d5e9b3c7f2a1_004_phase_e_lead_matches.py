"""004_phase_e_lead_matches

Revision ID: d5e9b3c7f2a1
Revises: c8f3a91e4d72
Create Date: 2026-06-02 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd5e9b3c7f2a1'
down_revision: Union[str, None] = 'c8f3a91e4d72'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'lead_matches',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('product_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('motivation_category_id', sa.UUID(), nullable=False),
        sa.Column('ocean_score', sa.Float(), nullable=False),
        sa.Column('embedding_score', sa.Float(), nullable=False),
        sa.Column('interest_score', sa.Float(), nullable=False),
        sa.Column('final_score', sa.Float(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='50.0'),
        sa.Column('is_best_match', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('rank', sa.Integer(), nullable=True),
        sa.Column('reasoning', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['motivation_category_id'], ['motivation_categories.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['discovered_users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'motivation_category_id', name='uq_lead_match_user_category'),
    )
    op.create_index(op.f('ix_lead_matches_product_id'), 'lead_matches', ['product_id'], unique=False)
    op.create_index(op.f('ix_lead_matches_user_id'), 'lead_matches', ['user_id'], unique=False)
    op.create_index(op.f('ix_lead_matches_motivation_category_id'), 'lead_matches', ['motivation_category_id'], unique=False)
    op.create_index(op.f('ix_lead_matches_final_score'), 'lead_matches', ['final_score'], unique=False)
    op.create_index(op.f('ix_lead_matches_is_best_match'), 'lead_matches', ['is_best_match'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_lead_matches_is_best_match'), table_name='lead_matches')
    op.drop_index(op.f('ix_lead_matches_final_score'), table_name='lead_matches')
    op.drop_index(op.f('ix_lead_matches_motivation_category_id'), table_name='lead_matches')
    op.drop_index(op.f('ix_lead_matches_user_id'), table_name='lead_matches')
    op.drop_index(op.f('ix_lead_matches_product_id'), table_name='lead_matches')
    op.drop_table('lead_matches')
