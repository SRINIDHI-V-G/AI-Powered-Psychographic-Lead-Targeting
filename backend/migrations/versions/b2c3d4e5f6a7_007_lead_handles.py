"""007_lead_handles

Creates:
  - lead_handles : discovered social handles for each pipeline user

Tier values (stored as plain String, no DB enum):
  confirmed  — handle found verbatim in bio/profile URL
  extracted  — @mention or URL parsed from bio text
  inferred   — derived from username transformation patterns
  predicted  — LLM / pattern-library candidate not yet verified

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-05 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lead_handles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("discovered_user_id", sa.UUID(), nullable=False),
        sa.Column("platform", sa.String(30), nullable=False),
        sa.Column("handle", sa.String(255), nullable=False),
        sa.Column("handle_score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="50.0"),
        # confirmed | extracted | inferred | predicted
        sa.Column("tier", sa.String(20), nullable=False, server_default="predicted"),
        # Evidence that drove generation/extraction of this handle
        # Schema: {"source": str, "raw_text": str, "generator": str, ...}
        sa.Column(
            "evidence_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        # Verification signals (populated after handle verification step)
        # Schema: {"verified": bool, "verification_method": str, "profile_exists": bool}
        sa.Column(
            "verification_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["discovered_user_id"],
            ["discovered_users.id"],
            ondelete="CASCADE",
            name="fk_lead_handles_discovered_user",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_lead_handles_discovered_user_id",
        "lead_handles",
        ["discovered_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_lead_handles_platform",
        "lead_handles",
        ["platform"],
        unique=False,
    )
    op.create_index(
        "ix_lead_handles_tier",
        "lead_handles",
        ["tier"],
        unique=False,
    )
    op.create_index(
        "ix_lead_handles_handle_score",
        "lead_handles",
        ["handle_score"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_lead_handles_handle_score", table_name="lead_handles")
    op.drop_index("ix_lead_handles_tier", table_name="lead_handles")
    op.drop_index("ix_lead_handles_platform", table_name="lead_handles")
    op.drop_index("ix_lead_handles_discovered_user_id", table_name="lead_handles")
    op.drop_table("lead_handles")
