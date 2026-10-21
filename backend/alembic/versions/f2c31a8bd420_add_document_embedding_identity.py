"""Add explicit embedding provider and model identity to documents.

Revision ID: f2c31a8bd420
Revises: d4b7a23c9f10
"""

from alembic import op
import sqlalchemy as sa


revision = "f2c31a8bd420"
down_revision = "d4b7a23c9f10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("embedding_provider", sa.String(50), nullable=True))
    op.add_column("documents", sa.Column("embedding_model", sa.String(255), nullable=True))
    # All vectors created before this migration came from the original Nomic pipeline.
    op.execute(
        "UPDATE documents SET embedding_provider = 'nomic_local', "
        "embedding_model = 'nomic-ai/nomic-embed-text-v1.5'"
    )
    op.alter_column("documents", "embedding_provider", nullable=False)
    op.alter_column("documents", "embedding_model", nullable=False)
    op.create_index(
        "ix_documents_embedding_identity",
        "documents",
        ["status", "embedding_provider", "embedding_model"],
    )


def downgrade() -> None:
    op.drop_index("ix_documents_embedding_identity", table_name="documents")
    op.drop_column("documents", "embedding_model")
    op.drop_column("documents", "embedding_provider")
