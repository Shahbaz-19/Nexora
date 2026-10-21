"""create documents and document chunks

Revision ID: e6b6a3c7896f
Revises: 08f671560a3b
Create Date: 2026-09-23 17:42:02.733443
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy


# revision identifiers, used by Alembic.
revision: str = "e6b6a3c7896f"
down_revision: Union[str, Sequence[str], None] = "08f671560a3b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create documents and document_chunks tables."""

    op.create_table(
        "documents",
        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "original_filename",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "file_type",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "file_size",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "UPLOADED",
                "PROCESSING",
                "READY",
                "FAILED",
                name="document_status",
            ),
            nullable=False,
        ),
        sa.Column(
            "failure_reason",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_documents_status"),
        "documents",
        ["status"],
        unique=False,
    )

    op.create_index(
        op.f("ix_documents_user_id"),
        "documents",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "document_chunks",
        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "chunk_index",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "token_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "page_number",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "section_title",
            sa.String(length=500),
            nullable=True,
        ),
        sa.Column(
            "embedding",
            pgvector.sqlalchemy.Vector(768),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_document_chunk_index",
        ),
    )

    op.create_index(
        op.f("ix_document_chunks_document_id"),
        "document_chunks",
        ["document_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove documents and document_chunks tables."""

    op.drop_index(
        op.f("ix_document_chunks_document_id"),
        table_name="document_chunks",
    )

    op.drop_table("document_chunks")

    op.drop_index(
        op.f("ix_documents_user_id"),
        table_name="documents",
    )

    op.drop_index(
        op.f("ix_documents_status"),
        table_name="documents",
    )

    op.drop_table("documents")

    document_status_enum = sa.Enum(
        "UPLOADED",
        "PROCESSING",
        "READY",
        "FAILED",
        name="document_status",
    )

    document_status_enum.drop(
        op.get_bind(),
        checkfirst=True,
    )