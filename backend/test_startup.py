import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


class StartupTests(unittest.TestCase):
    @patch("app.main.warm_up_reranker_model")
    @patch("app.main.warm_up_embedding_model")
    def test_cloud_startup_does_not_warm_local_models(self, embedding, reranker):
        cloud = SimpleNamespace(
            stale_processing_minutes=30,
            embedding_provider="gemini",
            reranker_provider="none",
        )
        with patch("app.main.settings", cloud), TestClient(app) as client:
            self.assertEqual(client.get("/health").status_code, 200)
        embedding.assert_not_called()
        reranker.assert_not_called()

    @patch("app.main.warm_up_reranker_model", return_value=0.045)
    @patch("app.main.warm_up_embedding_model", return_value=0.123)
    def test_local_models_are_warmed(self, embedding, reranker):
        local = SimpleNamespace(
            stale_processing_minutes=30,
            embedding_provider="nomic_local",
            reranker_provider="local",
        )
        with (
            patch("app.main.settings", local),
            patch("app.main.active_embedding_description", return_value="nomic_local:model"),
            TestClient(app) as client,
        ):
            self.assertEqual(client.get("/health").status_code, 200)
        embedding.assert_called_once_with()
        reranker.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
