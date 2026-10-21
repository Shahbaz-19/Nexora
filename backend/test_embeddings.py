import math
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.rag.embeddings import (
    EMBEDDING_DIMENSION,
    GeminiEmbeddingProvider,
    _normalize_and_validate,
)


def raw_vector(value: float = 1.0):
    return [value] * EMBEDDING_DIMENSION


class GeminiEmbeddingTests(unittest.TestCase):
    def response(self, count: int):
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=raw_vector(index + 1)) for index in range(count)]
        )

    def test_document_batches_use_retrieval_document_and_768_dimensions(self):
        client = Mock()
        client.models.embed_content.side_effect = [self.response(2), self.response(1)]
        provider = GeminiEmbeddingProvider()
        with patch.object(provider, "_client", return_value=client):
            vectors = provider.embed_documents(["one", "two", "three"], batch_size=2)

        self.assertEqual(len(vectors), 3)
        self.assertTrue(all(len(vector) == EMBEDDING_DIMENSION for vector in vectors))
        self.assertTrue(all(math.isclose(sum(v * v for v in vector), 1.0) for vector in vectors))
        for call in client.models.embed_content.call_args_list:
            self.assertEqual(call.kwargs["config"].task_type, "RETRIEVAL_DOCUMENT")
            self.assertEqual(call.kwargs["config"].output_dimensionality, 768)

    def test_query_uses_retrieval_query(self):
        client = Mock()
        client.models.embed_content.return_value = self.response(1)
        provider = GeminiEmbeddingProvider()
        with patch.object(provider, "_client", return_value=client):
            provider.embed_query("coolant pressure")
        config = client.models.embed_content.call_args.kwargs["config"]
        self.assertEqual(config.task_type, "RETRIEVAL_QUERY")

    def test_invalid_dimensions_and_non_finite_values_are_rejected(self):
        with self.assertRaises(RuntimeError):
            _normalize_and_validate([1.0] * 767)
        invalid = raw_vector()
        invalid[4] = float("nan")
        with self.assertRaises(RuntimeError):
            _normalize_and_validate(invalid)

    def test_api_errors_propagate_after_sdk_retry_handling(self):
        client = Mock()
        client.models.embed_content.side_effect = RuntimeError("rate limited")
        provider = GeminiEmbeddingProvider()
        with patch.object(provider, "_client", return_value=client):
            with self.assertRaisesRegex(RuntimeError, "rate limited"):
                provider.embed_query("query")

    def test_client_configures_timeout_and_transient_retries(self):
        from google import genai

        GeminiEmbeddingProvider._client.cache_clear()
        with patch.object(genai, "Client", return_value=Mock()) as constructor:
            GeminiEmbeddingProvider._client()
        options = constructor.call_args.kwargs["http_options"]
        self.assertGreater(options.timeout, 0)
        self.assertEqual(options.retry_options.attempts, 4)
        self.assertIn(429, options.retry_options.http_status_codes)
        GeminiEmbeddingProvider._client.cache_clear()


if __name__ == "__main__":
    unittest.main()
