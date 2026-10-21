import unittest
from uuid import uuid4
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.main import app
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.rag.embeddings import EMBEDDING_DIMENSION
from app.rag.ingestion import process_document_ingestion
from app.rag.retrieval import retrieve_chunks


def embedding(value: float = 0.01) -> list[float]:
    return [value] * EMBEDDING_DIMENSION


class DocumentManagementTests(unittest.TestCase):
    def setUp(self):
        self.connection = engine.connect()
        self.transaction = self.connection.begin()
        self.db = Session(bind=self.connection, join_transaction_mode="create_savepoint")
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

        self.user_a = self.register_and_login("a")
        self.user_b = self.register_and_login("b")

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.db.close()
        self.transaction.rollback()
        self.connection.close()

    def register_and_login(self, suffix: str):
        credentials = {
            "email": f"documents-{suffix}-{uuid4().hex}@example.com",
            "password": "DocumentTest-123!",
        }
        created = self.client.post(
            "/auth/register",
            json={**credentials, "full_name": f"Document User {suffix}"},
        )
        self.assertEqual(created.status_code, 201, created.text)
        login = self.client.post("/auth/login", json=credentials)
        self.assertEqual(login.status_code, 200, login.text)
        return {
            "id": created.json()["id"],
            "headers": {"Authorization": f"Bearer {login.json()['access_token']}"},
        }

    def create_document(
        self,
        user_id: int,
        filename: str = "manual.txt",
        status: DocumentStatus = DocumentStatus.READY,
        chunks: int = 1,
    ) -> Document:
        document = Document(
            user_id=user_id,
            original_filename=filename,
            file_type="txt",
            file_size=128,
            status=status,
            failure_reason="Parse failed." if status == DocumentStatus.FAILED else None,
        )
        self.db.add(document)
        self.db.flush()
        for index in range(chunks):
            self.db.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=index,
                    content=f"{filename} chunk {index}",
                    token_count=10,
                    page_number=None,
                    section_title=None,
                    embedding=embedding(0.01 + index / 100),
                )
            )
        self.db.commit()
        self.db.refresh(document)
        return document

    def test_authenticated_list_detail_and_chunk_count(self):
        first = self.create_document(self.user_a["id"], "first.txt", chunks=2)
        second = self.create_document(self.user_a["id"], "second.txt", chunks=1)
        self.create_document(self.user_b["id"], "other.txt", chunks=3)

        listed = self.client.get("/documents", headers=self.user_a["headers"])
        self.assertEqual(listed.status_code, 200, listed.text)
        ids = {item["id"] for item in listed.json()}
        self.assertEqual(ids, {first.id, second.id})
        counts = {item["id"]: item["chunk_count"] for item in listed.json()}
        self.assertEqual(counts[first.id], 2)
        self.assertEqual(counts[second.id], 1)
        self.assertNotIn("embedding", listed.text)
        self.assertNotIn("content", listed.text)

        detail = self.client.get(f"/documents/{first.id}", headers=self.user_a["headers"])
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["id"], first.id)
        self.assertEqual(detail.json()["chunk_count"], 2)

    def test_ownership_isolation_for_list_detail_and_delete(self):
        document = self.create_document(self.user_a["id"], "private.txt", chunks=2)

        self.assertEqual(self.client.get("/documents", headers=self.user_b["headers"]).json(), [])
        self.assertEqual(
            self.client.get(f"/documents/{document.id}", headers=self.user_b["headers"]).status_code,
            404,
        )
        self.assertEqual(
            self.client.delete(f"/documents/{document.id}", headers=self.user_b["headers"]).status_code,
            404,
        )
        self.assertIsNotNone(self.db.get(Document, document.id))

    def test_successful_delete_cascades_chunks(self):
        document = self.create_document(self.user_a["id"], "delete-me.txt", chunks=3)
        chunk_ids = list(
            self.db.scalars(
                select(DocumentChunk.id).where(DocumentChunk.document_id == document.id)
            )
        )

        response = self.client.delete(f"/documents/{document.id}", headers=self.user_a["headers"])

        self.assertEqual(response.status_code, 204, response.text)
        self.assertIsNone(self.db.get(Document, document.id))
        self.assertEqual(
            list(self.db.scalars(select(DocumentChunk.id).where(DocumentChunk.id.in_(chunk_ids)))),
            [],
        )

    @patch(
        "app.rag.retrieval.rerank_candidates",
        side_effect=lambda query, candidates, top_k: list(candidates)[:top_k],
    )
    @patch("app.rag.retrieval.embed_query", return_value=embedding())
    def test_retrieval_only_uses_ready_documents(self, embed, rerank):
        ready = self.create_document(self.user_a["id"], "ready.txt", DocumentStatus.READY)
        self.create_document(self.user_a["id"], "failed.txt", DocumentStatus.FAILED)
        self.create_document(self.user_a["id"], "processing.txt", DocumentStatus.PROCESSING)
        self.create_document(self.user_a["id"], "uploaded.txt", DocumentStatus.UPLOADED)

        results = retrieve_chunks(self.db, self.user_a["id"], "coolant pressure", top_k=10)

        self.assertTrue(results)
        self.assertEqual({result.document_id for result in results}, {ready.id})

    @patch("starlette.background.BackgroundTasks.add_task")
    def test_async_upload_returns_processing_and_schedules_ingestion(self, add_task):
        response = self.client.post(
            "/documents/upload",
            headers=self.user_a["headers"],
            files={"file": ("upload.txt", b"Useful engineering text.", "text/plain")},
        )

        self.assertEqual(response.status_code, 202, response.text)
        payload = response.json()
        self.assertEqual(payload["status"], "PROCESSING")
        self.assertEqual(payload["chunk_count"], 0)
        self.assertEqual(payload["original_filename"], "upload.txt")
        document = self.db.get(Document, payload["id"])
        self.assertIsNotNone(document)
        self.assertEqual(document.status, DocumentStatus.PROCESSING)
        add_task.assert_called_once()
        self.assertEqual(add_task.call_args.args[1], payload["id"])
        self.assertEqual(add_task.call_args.args[2], b"Useful engineering text.")

    @patch("app.rag.ingestion.ingest_document")
    @patch("app.rag.ingestion.SessionLocal")
    def test_background_success_marks_document_ready(self, session_local, ingest):
        document = self.create_document(
            self.user_a["id"],
            "background-success.txt",
            status=DocumentStatus.PROCESSING,
            chunks=0,
        )
        background_db = Session(bind=self.connection, join_transaction_mode="create_savepoint")
        background_db.close = Mock(wraps=background_db.close)
        session_local.return_value = background_db

        def fake_ingest(db, document, file_bytes):
            document.status = DocumentStatus.READY
            document.failure_reason = None
            db.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=0,
                    content="Background content",
                    token_count=2,
                    page_number=None,
                    section_title=None,
                    embedding=embedding(),
                )
            )
            db.commit()
            return 1

        ingest.side_effect = fake_ingest

        process_document_ingestion(document.id, b"Background content")

        self.db.expire_all()
        updated = self.db.get(Document, document.id)
        self.assertEqual(updated.status, DocumentStatus.READY)
        self.assertEqual(
            self.db.scalar(
                select(DocumentChunk).where(DocumentChunk.document_id == document.id)
            ).content,
            "Background content",
        )
        background_db.close.assert_called_once()

    @patch("app.rag.ingestion.embed_documents")
    @patch("app.rag.ingestion.parse_document")
    @patch("app.rag.ingestion.logger.exception")
    @patch("app.rag.ingestion.SessionLocal")
    def test_background_failure_marks_document_failed(
        self,
        session_local,
        log_exception,
        parse_document,
        embed,
    ):
        document = self.create_document(
            self.user_a["id"],
            "background-failure.txt",
            status=DocumentStatus.PROCESSING,
            chunks=0,
        )
        background_db = Session(bind=self.connection, join_transaction_mode="create_savepoint")
        background_db.close = Mock(wraps=background_db.close)
        session_local.return_value = background_db
        parse_document.side_effect = ValueError("Unreadable document")

        process_document_ingestion(document.id, b"bad")

        self.db.expire_all()
        updated = self.db.get(Document, document.id)
        self.assertEqual(updated.status, DocumentStatus.FAILED)
        self.assertIn("Unreadable document", updated.failure_reason)
        embed.assert_not_called()
        log_exception.assert_called_once()
        background_db.close.assert_called_once()

    @patch("app.rag.ingestion.ingest_document")
    @patch("app.rag.ingestion.SessionLocal")
    def test_background_task_uses_independent_db_session(self, session_local, ingest):
        document = self.create_document(
            self.user_a["id"],
            "session.txt",
            status=DocumentStatus.PROCESSING,
            chunks=0,
        )
        background_db = Session(bind=self.connection, join_transaction_mode="create_savepoint")
        background_db.close = Mock(wraps=background_db.close)
        session_local.return_value = background_db

        process_document_ingestion(document.id, b"content")

        ingest.assert_called_once()
        used_db = ingest.call_args.kwargs["db"]
        self.assertIs(used_db, background_db)
        self.assertIsNot(used_db, self.db)
        background_db.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
