import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.rag.reranker import rerank_candidates, warm_up_reranker_model


def candidate(chunk_id: int, content: str):
    return SimpleNamespace(chunk=SimpleNamespace(id=chunk_id, content=content))


class RerankerTests(unittest.TestCase):
    def setUp(self):
        self.settings_patcher = patch(
            "app.rag.reranker.settings",
            SimpleNamespace(reranker_provider="local"),
        )
        self.settings_patcher.start()

    def tearDown(self):
        self.settings_patcher.stop()

    @patch("app.rag.reranker.rerank_candidate_scores", return_value=[0.2, 0.9, 0.5])
    def test_rerank_candidates_uses_scores_and_final_top_k(self, scores):
        candidates = [
            candidate(1, "first"),
            candidate(2, "second"),
            candidate(3, "third"),
        ]

        results = rerank_candidates("query", candidates, top_k=2)

        self.assertEqual([item.chunk.id for item in results], [2, 3])
        scores.assert_called_once_with("query", ["first", "second", "third"])

    @patch("app.rag.reranker.rerank_candidate_scores", return_value=[0.8, 0.8, 0.2])
    def test_tied_scores_preserve_candidate_order(self, scores):
        candidates = [
            candidate(1, "first"),
            candidate(2, "second"),
            candidate(3, "third"),
        ]

        results = rerank_candidates("query", candidates, top_k=3)

        self.assertEqual([item.chunk.id for item in results], [1, 2, 3])

    @patch("app.rag.reranker.rerank_candidate_scores", return_value=[0.1])
    def test_warmup_runs_one_prediction(self, scores):
        elapsed = warm_up_reranker_model()

        self.assertGreaterEqual(elapsed, 0)
        scores.assert_called_once()


if __name__ == "__main__":
    unittest.main()
