from functools import lru_cache
from time import perf_counter
from typing import Any, Protocol, Sequence, TypeVar

from app.core.config import settings


RERANKER_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"
RERANKER_WARMUP_QUERY = "reranker startup warmup"
RERANKER_WARMUP_PASSAGE = "Nexora reranker warmup passage."


class RerankableCandidate(Protocol):
    chunk: object


CandidateT = TypeVar("CandidateT", bound=RerankableCandidate)


@lru_cache(maxsize=1)
def get_reranker_model() -> Any:
    if settings.reranker_provider != "local":
        raise RuntimeError("The local reranker is disabled.")
    from sentence_transformers import CrossEncoder

    return CrossEncoder(RERANKER_MODEL_NAME)


def rerank_candidate_scores(query: str, passages: Sequence[str]) -> list[float]:
    if not passages:
        return []
    scores = get_reranker_model().predict([(query, passage) for passage in passages])
    return [float(score) for score in scores]


def rerank_candidates(
    query: str, candidates: Sequence[CandidateT], top_k: int
) -> list[CandidateT]:
    if top_k <= 0:
        raise ValueError("top_k must be greater than 0.")
    if not candidates:
        return []
    if settings.reranker_provider == "none":
        return list(candidates[:top_k])

    passages = [str(candidate.chunk.content) for candidate in candidates]
    scores = rerank_candidate_scores(query, passages)
    if len(scores) != len(candidates):
        raise RuntimeError("Reranker score count does not match candidate count.")
    ranked = sorted(
        zip(candidates, scores, range(len(candidates)), strict=True),
        key=lambda item: (-item[1], item[2]),
    )
    return [candidate for candidate, _score, _index in ranked[:top_k]]


def warm_up_reranker_model() -> float:
    if settings.reranker_provider == "none":
        return 0.0
    start = perf_counter()
    scores = rerank_candidate_scores(
        RERANKER_WARMUP_QUERY, [RERANKER_WARMUP_PASSAGE]
    )
    if len(scores) != 1:
        raise RuntimeError("Reranker warmup did not return exactly one score.")
    return perf_counter() - start
