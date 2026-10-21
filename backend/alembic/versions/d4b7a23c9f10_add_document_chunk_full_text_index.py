"""Add full-text index for hybrid retrieval."""

from alembic import op


revision = "d4b7a23c9f10"
down_revision = "c7a921de4501"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_document_chunks_content_fts_simple
        ON document_chunks
        USING gin (to_tsvector('simple', content))
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS ix_document_chunks_content_fts_simple
        """
    )
