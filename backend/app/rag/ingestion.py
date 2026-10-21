import logging

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.rag.chunking import chunk_text
from app.rag.embeddings import embed_documents, embedding_identity
from app.rag.parsers import parse_document


logger = logging.getLogger("uvicorn.error")


def ingest_document(
    db: Session,
    document: Document,
    file_bytes: bytes,
) -> int:
    document.status = DocumentStatus.PROCESSING
    document.failure_reason = None
    db.commit()

    try:
        sections = parse_document(
            filename=document.original_filename,
            file_bytes=file_bytes,
        )

        chunk_records: list[dict] = []
        global_chunk_index = 0

        for section in sections:
            chunks = chunk_text(section.content)

            for chunk in chunks:
                chunk_records.append(
                    {
                        "content": chunk.content,
                        "chunk_index": global_chunk_index,
                        "token_count": chunk.token_count,
                        "page_number": section.page_number,
                    }
                )

                global_chunk_index += 1

        if not chunk_records:
            raise ValueError(
                "The document did not produce any usable chunks."
            )

        embeddings = embed_documents(
            [
                record["content"]
                for record in chunk_records
            ]
        )

        if len(embeddings) != len(chunk_records):
            raise RuntimeError(
                "Embedding count does not match chunk count."
            )

        document_chunks = [
            DocumentChunk(
                document_id=document.id,
                chunk_index=record["chunk_index"],
                content=record["content"],
                token_count=record["token_count"],
                page_number=record["page_number"],
                section_title=None,
                embedding=embedding,
            )
            for record, embedding in zip(
                chunk_records,
                embeddings,
                strict=True,
            )
        ]

        db.add_all(document_chunks)

        document.embedding_provider, document.embedding_model = embedding_identity()
        document.status = DocumentStatus.READY
        document.failure_reason = None

        db.commit()

        return len(document_chunks)

    except Exception as exc:
        db.rollback()

        document.status = DocumentStatus.FAILED
        document.failure_reason = str(exc)

        db.add(document)
        db.commit()

        raise


def process_document_ingestion(
    document_id: int,
    file_bytes: bytes,
) -> None:
    """
    Process an uploaded document outside the request lifecycle.

    Background tasks must own their own database session because the request
    scoped session is closed once the upload response is returned.
    """
    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document is None:
            return

        ingest_document(
            db=db,
            document=document,
            file_bytes=file_bytes,
        )
    except Exception:
        logger.exception(
            "Background document ingestion failed | document_id=%s",
            document_id,
        )
    finally:
        db.close()
