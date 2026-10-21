import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy.orm import Session

from app.database import engine
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.models.user import User
from app.rag.embeddings import EMBEDDING_DIMENSION, embedding_identity
from app.rag.reindex import reindex_document


def vector(value: float) -> list[float]:
    return [value] * EMBEDDING_DIMENSION


class ReindexTests(unittest.TestCase):
    def setUp(self):
        self.connection = engine.connect()
        self.transaction = self.connection.begin()
        self.db = Session(bind=self.connection, join_transaction_mode="create_savepoint")
        user = User(
            email=f"reindex-{uuid4().hex}@example.com",
            full_name="Reindex User",
            hashed_password="unused",
        )
        self.db.add(user)
        self.db.flush()
        self.document = Document(
            user_id=user.id,
            original_filename="legacy.txt",
            file_type="txt",
            file_size=20,
            status=DocumentStatus.READY,
            embedding_provider="nomic_local",
            embedding_model="nomic-ai/nomic-embed-text-v1.5",
        )
        self.db.add(self.document)
        self.db.flush()
        self.chunks = []
        for index in range(2):
            chunk = DocumentChunk(
                document_id=self.document.id,
                chunk_index=index,
                content=f"legacy content {index}",
                token_count=3,
                page_number=None,
                section_title=None,
                embedding=vector(0.01 + index / 100),
            )
            self.db.add(chunk)
            self.chunks.append(chunk)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.transaction.rollback()
        self.connection.close()

    @patch("app.rag.reindex.embed_documents")
    def test_success_replaces_all_vectors_and_identity_atomically(self, embed):
        embed.return_value = [vector(0.2), vector(0.3)]
        count = reindex_document(self.db, self.document.id)
        self.assertEqual(count, 2)
        refreshed = self.db.get(Document, self.document.id)
        self.assertEqual(
            (refreshed.embedding_provider, refreshed.embedding_model),
            embedding_identity(),
        )
        self.assertAlmostEqual(float(self.db.get(DocumentChunk, self.chunks[0].id).embedding[0]), 0.2)

    @patch("app.rag.reindex.embed_documents", side_effect=RuntimeError("quota exhausted"))
    def test_embedding_failure_preserves_old_vectors_and_identity(self, _embed):
        with self.assertRaisesRegex(RuntimeError, "quota exhausted"):
            reindex_document(self.db, self.document.id)
        refreshed = self.db.get(Document, self.document.id)
        self.assertEqual(refreshed.embedding_provider, "nomic_local")
        self.assertAlmostEqual(float(self.db.get(DocumentChunk, self.chunks[0].id).embedding[0]), 0.01)


if __name__ == "__main__":
    unittest.main()
