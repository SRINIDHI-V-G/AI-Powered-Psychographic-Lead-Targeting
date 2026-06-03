"""005_pgvector_embeddings

Adds native pgvector VECTOR(384) column to user_embeddings alongside the
existing JSONB column.  The JSONB column is retained for backward compatibility
and will be dropped in a future migration once all rows have been backfilled.

Revision ID: e2f4b8c1d9a5
Revises: d5e9b3c7f2a1
Create Date: 2026-06-03 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision: str = "e2f4b8c1d9a5"
down_revision: Union[str, None] = "d5e9b3c7f2a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable the pgvector extension (idempotent — safe to run multiple times)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Add the native vector column alongside the existing JSONB column.
    # Nullable because existing rows don't have a vector yet.
    op.add_column(
        "user_embeddings",
        sa.Column(
            "embedding_vector",
            sa.Text(),       # placeholder — altered to VECTOR(384) below
            nullable=True,
        ),
    )

    # ALTER the column to the proper VECTOR type now that the extension is enabled.
    # Using raw SQL because SQLAlchemy's DDL layer doesn't know about VECTOR.
    op.execute("ALTER TABLE user_embeddings ALTER COLUMN embedding_vector TYPE vector(384) USING NULL")

    # Backfill: convert existing JSONB embeddings to native VECTOR.
    # The JSONB values are arrays of floats; cast them via text representation.
    # This runs in a single UPDATE — acceptable for typical row counts (<50k).
    # For very large tables, run this outside the migration as a background job.
    op.execute(
        """
        UPDATE user_embeddings
        SET embedding_vector = embedding::text::vector
        WHERE embedding IS NOT NULL
          AND embedding_vector IS NULL
        """
    )

    # Create an IVFFlat index for approximate nearest-neighbour cosine search.
    # IVFFlat requires data to exist before training; if the table is empty the
    # index builds instantly and will be re-trained as data is inserted.
    # lists=100 is appropriate for tables up to ~1M rows; tune for larger datasets.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_user_embeddings_vector_cosine
        ON user_embeddings
        USING ivfflat (embedding_vector vector_cosine_ops)
        WITH (lists = 100)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_user_embeddings_vector_cosine")
    op.drop_column("user_embeddings", "embedding_vector")
    # Note: we intentionally do NOT drop the vector extension on downgrade
    # because other tables or tools may depend on it.
