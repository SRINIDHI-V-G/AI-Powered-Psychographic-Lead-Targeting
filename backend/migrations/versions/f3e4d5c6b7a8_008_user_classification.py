"""008_user_classification

Adds account-type classification columns to discovered_users.

New columns:
  account_type            — buyer | enthusiast | community | creator |
                            business | store | competitor | unknown
  account_type_confidence — float 0.0–1.0
  account_type_signals    — JSONB list of signal tags that fired
  pipeline_excluded       — True for business/store/competitor accounts
                            (NLP, OCEAN, matching services skip these rows)
  exclusion_reason        — human-readable exclusion note

Revision ID: f3e4d5c6b7a8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-10 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f3e4d5c6b7a8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "discovered_users",
        sa.Column(
            "account_type",
            sa.String(20),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.add_column(
        "discovered_users",
        sa.Column(
            "account_type_confidence",
            sa.Float(),
            nullable=False,
            server_default="0.0",
        ),
    )
    op.add_column(
        "discovered_users",
        sa.Column(
            "account_type_signals",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "discovered_users",
        sa.Column(
            "pipeline_excluded",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "discovered_users",
        sa.Column(
            "exclusion_reason",
            sa.Text(),
            nullable=True,
        ),
    )
    # Index for fast lookup of non-excluded users (the common query path)
    op.create_index(
        "ix_discovered_users_pipeline_excluded",
        "discovered_users",
        ["pipeline_excluded"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_discovered_users_pipeline_excluded",
        table_name="discovered_users",
    )
    op.drop_column("discovered_users", "exclusion_reason")
    op.drop_column("discovered_users", "pipeline_excluded")
    op.drop_column("discovered_users", "account_type_signals")
    op.drop_column("discovered_users", "account_type_confidence")
    op.drop_column("discovered_users", "account_type")
