import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy.orm import Session

from app.database import engine
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.models.user import User
from app.rag.embeddings import EMBEDDING_DIMENSION
from app.rag.retrieval import (
    RRF_K,
    RERANK_CANDIDATE_COUNT,
    RetrievalCandidate,
    branch_candidate_limit,
    reciprocal_rank_fusion,
    rerank_candidate_limit,
    retrieve_chunks,
)


def vector(first: float = 1.0, second: float = 0.0) -> list[float]:
    values = [0.0] * EMBEDDING_DIMENSION
    values[0] = first
    values[1] = second
    return values


class HybridRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.connection = engine.connect()
        self.transaction = self.connection.begin()
        self.db = Session(bind=self.connection, join_transaction_mode="create_savepoint")
        self.user_a = self.create_user("a")
        self.user_b = self.create_user("b")
        self.rerank_patcher = patch(
            "app.rag.retrieval.rerank_candidates",
            side_effect=lambda query, candidates, top_k: list(candidates)[:top_k],
        )
        self.rerank = self.rerank_patcher.start()

    def tearDown(self):
        self.rerank_patcher.stop()
        self.db.close()
        self.transaction.rollback()
        self.connection.close()

    def create_user(self, suffix: str) -> User:
        user = User(
            email=f"hybrid-{suffix}-{uuid4().hex}@example.com",
            full_name=f"Hybrid User {suffix}",
            hashed_password="unused",
        )
        self.db.add(user)
        self.db.flush()
        return user

    def add_chunk(
        self,
        user: User,
        content: str,
        embedding: list[float],
        *,
        status: DocumentStatus = DocumentStatus.READY,
        filename: str | None = None,
        chunk_index: int = 0,
        embedding_provider: str | None = None,
        embedding_model: str | None = None,
    ) -> DocumentChunk:
        document = Document(
            user_id=user.id,
            original_filename=filename or f"doc-{uuid4().hex}.txt",
            file_type="txt",
            file_size=len(content),
            status=status,
            **({"embedding_provider": embedding_provider} if embedding_provider else {}),
            **({"embedding_model": embedding_model} if embedding_model else {}),
        )
        self.db.add(document)
        self.db.flush()
        chunk = DocumentChunk(
            document_id=document.id,
            chunk_index=chunk_index,
            content=content,
            token_count=max(1, len(content.split())),
            page_number=None,
            section_title=None,
            embedding=embedding,
        )
        self.db.add(chunk)
        self.db.commit()
        self.db.refresh(chunk)
        return chunk

    @patch("app.rag.retrieval.embed_query", return_value=vector())
    def test_incompatible_embedding_space_is_excluded(self, _embed):
        from app.rag.embeddings import embedding_identity

        provider, model = embedding_identity()
        compatible = self.add_chunk(self.user_a, "compatible pressure", vector())
        self.add_chunk(
            self.user_a,
            "incompatible pressure",
            vector(),
            embedding_provider="nomic_local" if provider != "nomic_local" else "gemini",
            embedding_model="different-model",
        )
        results = retrieve_chunks(self.db, self.user_a.id, "pressure", top_k=5)
        self.assertEqual([item.chunk_id for item in results], [compatible.id])

    @patch("app.rag.retrieval.embed_query", return_value=vector(1.0, 0.0))
    def test_semantic_only_match(self, embed):
        target = self.add_chunk(
            self.user_a,
            "A conceptually relevant passage without the query words.",
            vector(1.0, 0.0),
            filename="semantic.txt",
        )
        self.add_chunk(
            self.user_a,
            "Unrelated material without lexical overlap.",
            vector(0.0, 1.0),
        )

        results = retrieve_chunks(self.db, self.user_a.id, "coolant pressure", top_k=1)

        self.assertEqual(results[0].chunk_id, target.id)

    @patch("app.rag.retrieval.embed_query", return_value=vector(1.0, 0.0))
    def test_lexical_exact_identifier_match(self, embed):
        self.add_chunk(
            self.user_a,
            "General high level engineering discussion.",
            vector(1.0, 0.0),
        )
        identifier = self.add_chunk(
            self.user_a,
            "Alarm ERR_5021 indicates the inverter latch is open.",
            vector(0.0, 1.0),
            filename="identifier.txt",
        )

        results = retrieve_chunks(self.db, self.user_a.id, "ERR_5021", top_k=1)

        self.assertEqual(results[0].chunk_id, identifier.id)

    def test_rrf_deduplicates_overlapping_results(self):
        chunk = SimpleNamespace(id=1)
        semantic = [RetrievalCandidate(chunk=chunk, filename="a", semantic_score=0.9)]
        lexical = [RetrievalCandidate(chunk=chunk, filename="a", lexical_score=0.5)]

        results = reciprocal_rank_fusion(semantic, lexical, top_k=5)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].semantic_score, 0.9)
        self.assertEqual(results[0].lexical_score, 0.5)

    def test_rrf_ordering_prefers_cross_branch_evidence(self):
        shared = RetrievalCandidate(chunk=SimpleNamespace(id=3), filename="shared")
        semantic_only = RetrievalCandidate(chunk=SimpleNamespace(id=1), filename="semantic")
        lexical_only = RetrievalCandidate(chunk=SimpleNamespace(id=2), filename="lexical")

        results = reciprocal_rank_fusion(
            semantic=[semantic_only, shared],
            lexical=[lexical_only, shared],
            top_k=3,
        )

        self.assertEqual(results[0].chunk.id, 3)
        self.assertGreater(2 * (1 / (RRF_K + 2)), 1 / (RRF_K + 1))

    @patch("app.rag.retrieval.embed_query", return_value=vector(1.0, 0.0))
    def test_user_isolation(self, embed):
        own = self.add_chunk(
            self.user_a,
            "refresh_jti appears in this user's authentication notes.",
            vector(1.0, 0.0),
            filename="own.txt",
        )
        self.add_chunk(
            self.user_b,
            "refresh_jti appears in another user's private notes.",
            vector(1.0, 0.0),
            filename="other.txt",
        )

        results = retrieve_chunks(self.db, self.user_a.id, "refresh_jti", top_k=5)

        self.assertEqual({result.chunk_id for result in results}, {own.id})

    @patch("app.rag.retrieval.embed_query", return_value=vector(1.0, 0.0))
    def test_ready_only_filtering(self, embed):
        ready = self.add_chunk(
            self.user_a,
            "P-17 coolant pressure calibration is available.",
            vector(1.0, 0.0),
            status=DocumentStatus.READY,
        )
        for status in (
            DocumentStatus.UPLOADED,
            DocumentStatus.PROCESSING,
            DocumentStatus.FAILED,
        ):
            self.add_chunk(
                self.user_a,
                f"P-17 should not be searchable for {status.value}.",
                vector(1.0, 0.0),
                status=status,
            )

        results = retrieve_chunks(self.db, self.user_a.id, "P-17", top_k=10)

        self.assertEqual({result.chunk_id for result in results}, {ready.id})

    @patch("app.rag.retrieval.embed_query", return_value=vector(1.0, 0.0))
    def test_top_k_is_respected(self, embed):
        for index in range(5):
            self.add_chunk(
                self.user_a,
                f"coolant pressure item {index}",
                vector(1.0, index / 10),
                chunk_index=index,
            )

        results = retrieve_chunks(self.db, self.user_a.id, "coolant pressure", top_k=2)

        self.assertEqual(len(results), 2)
        self.rerank.assert_called()
        self.assertEqual(self.rerank.call_args.kwargs["top_k"], 2)

    @patch("app.rag.retrieval.embed_query", return_value=vector(1.0, 0.0))
    def test_reranker_reorders_fused_candidates_before_final_top_k(self, embed):
        self.rerank_patcher.stop()
        chunks = [
            self.add_chunk(
                self.user_a,
                f"coolant pressure candidate {index}",
                vector(1.0, index / 10),
                chunk_index=index,
            )
            for index in range(3)
        ]

        def fake_rerank(query, candidates, top_k):
            ranked = sorted(
                candidates,
                key=lambda candidate: {
                    chunks[0].id: 0.1,
                    chunks[1].id: 0.9,
                    chunks[2].id: 0.2,
                }[candidate.chunk.id],
                reverse=True,
            )
            return ranked[:top_k]

        try:
            with patch("app.rag.retrieval.rerank_candidates", side_effect=fake_rerank) as rerank:
                results = retrieve_chunks(self.db, self.user_a.id, "coolant pressure", top_k=1)
        finally:
            self.rerank = self.rerank_patcher.start()

        self.assertEqual(results[0].chunk_id, chunks[1].id)
        rerank.assert_called_once()
        self.assertEqual(rerank.call_args.kwargs["top_k"], 1)
        self.assertGreaterEqual(
            len(rerank.call_args.kwargs["candidates"]),
            len(chunks),
        )

    @patch("app.rag.retrieval.embed_query", return_value=vector(0.0, 1.0))
    def test_technical_identifiers_use_simple_text_search(self, embed):
        target = self.add_chunk(
            self.user_a,
            "P-17 ERR_5021 refresh_jti auth_sessions vector_cosine_ops",
            vector(0.0, 1.0),
            filename="technical-identifiers.txt",
        )

        for query in ("P-17", "ERR_5021", "refresh_jti", "auth_sessions", "vector_cosine_ops"):
            with self.subTest(query=query):
                results = retrieve_chunks(self.db, self.user_a.id, query, top_k=1)
                self.assertEqual(results[0].chunk_id, target.id)

    def test_candidate_depth(self):
        self.assertEqual(RERANK_CANDIDATE_COUNT, 20)
        self.assertEqual(rerank_candidate_limit(1), 20)
        self.assertEqual(rerank_candidate_limit(25), 25)
        self.assertEqual(branch_candidate_limit(1), 20)
        self.assertEqual(branch_candidate_limit(10), 40)


if __name__ == "__main__":
    unittest.main()
