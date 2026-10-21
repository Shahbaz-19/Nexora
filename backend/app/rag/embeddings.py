"""Configurable, validated embedding providers used by ingestion and retrieval."""

from __future__ import annotations

import math
import re
from functools import lru_cache
from time import perf_counter
from typing import Any, Protocol

from app.core.config import settings


EMBEDDING_DIMENSION = 768
NOMIC_MODEL_NAME = "nomic-ai/nomic-embed-text-v1.5"
DOCUMENT_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "
WARMUP_QUERY = "embedding model startup warmup"


class EmbeddingProvider(Protocol):
    provider_name: str
    model_name: str

    def embed_documents(self, texts: list[str], batch_size: int) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...
    def count_tokens(self, text: str) -> int: ...
    def warm_up(self) -> float: ...


def _normalize_and_validate(values: Any) -> list[float]:
    vector = [float(value) for value in values]
    if len(vector) != EMBEDDING_DIMENSION:
        raise RuntimeError(
            f"Embedding returned {len(vector)} dimensions; expected {EMBEDDING_DIMENSION}."
        )
    if not all(math.isfinite(value) for value in vector):
        raise RuntimeError("Embedding contains a non-finite value.")
    magnitude = math.sqrt(sum(value * value for value in vector))
    if not math.isfinite(magnitude) or magnitude <= 0:
        raise RuntimeError("Embedding has an invalid zero magnitude.")
    return [value / magnitude for value in vector]


class GeminiEmbeddingProvider:
    provider_name = "gemini"

    def __init__(self) -> None:
        self.model_name = settings.gemini_embedding_model

    @staticmethod
    @lru_cache(maxsize=1)
    def _client():
        from google import genai
        from google.genai import types

        retry = types.HttpRetryOptions(
            attempts=4,
            initial_delay=1.0,
            exp_base=2.0,
            max_delay=8.0,
            jitter=0.5,
            http_status_codes=[408, 429, 500, 502, 503, 504],
        )
        return genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(
                api_version="v1beta",
                timeout=int(settings.embedding_request_timeout_seconds * 1000),
                retry_options=retry,
            ),
        )

    def _embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        from google.genai import types

        response = self._client().models.embed_content(
            model=self.model_name,
            contents=texts,
            config=types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=EMBEDDING_DIMENSION,
            ),
        )
        embeddings = response.embeddings or []
        if len(embeddings) != len(texts):
            raise RuntimeError(
                f"Gemini returned {len(embeddings)} embeddings for {len(texts)} inputs."
            )
        return [_normalize_and_validate(item.values or []) for item in embeddings]

    def embed_documents(self, texts: list[str], batch_size: int) -> list[list[float]]:
        output: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            output.extend(
                self._embed(texts[start : start + batch_size], "RETRIEVAL_DOCUMENT")
            )
        return output

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], "RETRIEVAL_QUERY")[0]

    def count_tokens(self, text: str) -> int:
        # This conservative estimate avoids an API call for every sentence and
        # keeps 500-token chunks well below gemini-embedding-001's input limit.
        if not text:
            return 0
        words = re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE)
        return max(len(words), math.ceil(len(text.encode("utf-8")) / 4))

    def warm_up(self) -> float:
        # Hosted inference has no process-local weights to preload.
        return 0.0


class NomicLocalEmbeddingProvider:
    provider_name = "nomic_local"
    model_name = NOMIC_MODEL_NAME

    @staticmethod
    @lru_cache(maxsize=1)
    def _model():
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(NOMIC_MODEL_NAME)

    @staticmethod
    @lru_cache(maxsize=1)
    def _tokenizer():
        from transformers import AutoTokenizer

        return AutoTokenizer.from_pretrained(NOMIC_MODEL_NAME)

    def embed_documents(self, texts: list[str], batch_size: int) -> list[list[float]]:
        result = self._model().encode(
            [f"{DOCUMENT_PREFIX}{text}" for text in texts],
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return [_normalize_and_validate(vector) for vector in result]

    def embed_query(self, text: str) -> list[float]:
        result = self._model().encode(
            f"{QUERY_PREFIX}{text}",
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return _normalize_and_validate(result)

    def count_tokens(self, text: str) -> int:
        return len(self._tokenizer().encode(text, add_special_tokens=False)) if text else 0

    def warm_up(self) -> float:
        start = perf_counter()
        self.embed_query(WARMUP_QUERY)
        return perf_counter() - start


@lru_cache(maxsize=1)
def get_embedding_provider() -> EmbeddingProvider:
    if settings.embedding_provider == "gemini":
        return GeminiEmbeddingProvider()
    return NomicLocalEmbeddingProvider()


def embedding_identity() -> tuple[str, str]:
    provider = get_embedding_provider()
    return provider.provider_name, provider.model_name


def count_tokens(text: str) -> int:
    return get_embedding_provider().count_tokens(text)


def embed_documents(texts: list[str], batch_size: int | None = None) -> list[list[float]]:
    if not texts:
        return []
    return get_embedding_provider().embed_documents(
        texts, batch_size or settings.embedding_batch_size
    )


def embed_query(text: str) -> list[float]:
    if not text or not text.strip():
        raise ValueError("Query text cannot be empty")
    return get_embedding_provider().embed_query(text)


def warm_up_embedding_model() -> float:
    return get_embedding_provider().warm_up()


def active_embedding_description() -> str:
    provider, model = embedding_identity()
    return f"{provider}:{model}"
