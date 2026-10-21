"""Explicit, failure-safe document re-indexing across embedding spaces."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.rag.embeddings import embed_documents, embedding_identity


@dataclass(frozen=True)
class ChunkSnapshot:
    id: int
    content: str


def reindex_document(db: Session, document_id: int) -> int:
    """Replace one document's vectors atomically after all new vectors exist."""
    document = db.scalar(select(Document).where(Document.id == document_id))
    if document is None:
        raise ValueError(f"Document {document_id} does not exist.")
    if document.status != DocumentStatus.READY:
        raise ValueError(f"Document {document_id} is not READY.")
    snapshots = [
        ChunkSnapshot(id=chunk.id, content=chunk.content)
        for chunk in db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
        )
    ]
    if not snapshots:
        raise ValueError(f"Document {document_id} has no chunks to re-index.")

    # Release the read transaction before the remote request. No database rows
    # are changed unless every embedding has already been produced and validated.
    db.rollback()
    embeddings = embed_documents([item.content for item in snapshots])
    if len(embeddings) != len(snapshots):
        raise RuntimeError("Embedding count does not match the document chunk count.")

    with db.begin():
        locked_document = db.scalar(
            select(Document).where(Document.id == document_id).with_for_update()
        )
        if locked_document is None or locked_document.status != DocumentStatus.READY:
            raise RuntimeError("Document changed while re-indexing; no vectors were replaced.")
        current_chunks = list(
            db.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.chunk_index)
                .with_for_update()
            )
        )
        if [(item.id, item.content) for item in current_chunks] != [
            (item.id, item.content) for item in snapshots
        ]:
            raise RuntimeError("Document chunks changed while re-indexing; no vectors were replaced.")
        for chunk, embedding in zip(current_chunks, embeddings, strict=True):
            chunk.embedding = embedding
        locked_document.embedding_provider, locked_document.embedding_model = embedding_identity()
        locked_document.failure_reason = None
    return len(snapshots)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Re-index READY documents with the configured embedding provider."
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--all", action="store_true", help="Re-index all incompatible documents.")
    target.add_argument("--document-id", type=int, action="append", help="Document ID; repeatable.")
    parser.add_argument("--force", action="store_true", help="Also re-index already compatible documents.")
    parser.add_argument("--yes", action="store_true", help="Confirm the embedding-space replacement.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.yes:
        print("Refusing to re-index without --yes.", file=sys.stderr)
        return 2
    provider_name, model_name = embedding_identity()
    with SessionLocal() as db:
        if args.all:
            statement = select(Document.id).where(Document.status == DocumentStatus.READY)
            if not args.force:
                statement = statement.where(
                    (Document.embedding_provider != provider_name)
                    | (Document.embedding_model != model_name)
                )
            document_ids = list(db.scalars(statement.order_by(Document.id)))
        else:
            document_ids = list(dict.fromkeys(args.document_id or []))

        print(f"Target embedding identity: {provider_name}:{model_name}")
        failures = 0
        for document_id in document_ids:
            try:
                count = reindex_document(db, document_id)
                print(f"Re-indexed document {document_id}: {count} chunks")
            except Exception as exc:
                db.rollback()
                failures += 1
                print(f"Failed document {document_id}: {exc}", file=sys.stderr)
        print(f"Completed: {len(document_ids) - failures} succeeded, {failures} failed")
        return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
