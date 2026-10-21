from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.rag.embeddings import embed_query, embedding_identity
from app.rag.reranker import rerank_candidates
from app.rag.timing import RAGTimings


DEFAULT_TOP_K = 5
HYBRID_CANDIDATE_MULTIPLIER = 4
MIN_BRANCH_CANDIDATES = 20
RERANK_CANDIDATE_COUNT = 20
RRF_K = 60
TEXT_SEARCH_CONFIG = "simple"


@dataclass
class RetrievalResult:
    chunk_id: int
    document_id: int
    filename: str
    chunk_index: int
    content: str
    token_count: int
    page_number: int | None
    section_title: str | None
    similarity_score: float


@dataclass
class RetrievalCandidate:
    chunk: DocumentChunk
    filename: str
    semantic_score: float | None = None
    lexical_score: float | None = None


def branch_candidate_limit(top_k: int) -> int:
    return max(top_k * HYBRID_CANDIDATE_MULTIPLIER, MIN_BRANCH_CANDIDATES)


def rerank_candidate_limit(top_k: int) -> int:
    return max(top_k, RERANK_CANDIDATE_COUNT)


def semantic_candidates(
    db: Session,
    user_id: int,
    query_embedding: list[float],
    limit: int,
) -> list[RetrievalCandidate]:
    distance = DocumentChunk.embedding.cosine_distance(query_embedding)
    provider_name, model_name = embedding_identity()

    statement = (
        select(
            DocumentChunk,
            Document.original_filename,
            distance.label("distance"),
        )
        .join(
            Document,
            Document.id == DocumentChunk.document_id,
        )
        .where(
            Document.user_id == user_id,
            Document.status == DocumentStatus.READY,
            Document.embedding_provider == provider_name,
            Document.embedding_model == model_name,
        )
        .order_by(distance)
        .limit(limit)
    )

    return [
        RetrievalCandidate(
            chunk=chunk,
            filename=filename,
            semantic_score=1.0 - float(cosine_distance),
        )
        for chunk, filename, cosine_distance in db.execute(statement).all()
    ]


def lexical_candidates(
    db: Session,
    user_id: int,
    query: str,
    limit: int,
) -> list[RetrievalCandidate]:
    document_vector = func.to_tsvector(TEXT_SEARCH_CONFIG, DocumentChunk.content)
    provider_name, model_name = embedding_identity()
    query_vector = func.plainto_tsquery(TEXT_SEARCH_CONFIG, query)
    rank = func.ts_rank_cd(document_vector, query_vector)

    statement = (
        select(
            DocumentChunk,
            Document.original_filename,
            rank.label("rank"),
        )
        .join(
            Document,
            Document.id == DocumentChunk.document_id,
        )
        .where(
            Document.user_id == user_id,
            Document.status == DocumentStatus.READY,
            Document.embedding_provider == provider_name,
            Document.embedding_model == model_name,
            document_vector.op("@@")(query_vector),
        )
        .order_by(rank.desc(), DocumentChunk.id.asc())
        .limit(limit)
    )

    return [
        RetrievalCandidate(
            chunk=chunk,
            filename=filename,
            lexical_score=float(rank_score),
        )
        for chunk, filename, rank_score in db.execute(statement).all()
    ]


def reciprocal_rank_fusion(
    semantic: list[RetrievalCandidate],
    lexical: list[RetrievalCandidate],
    top_k: int,
) -> list[RetrievalCandidate]:
    by_chunk_id: dict[int, RetrievalCandidate] = {}
    scores: dict[int, float] = {}

    for ranking in (semantic, lexical):
        for rank, candidate in enumerate(ranking, start=1):
            chunk_id = candidate.chunk.id
            existing = by_chunk_id.get(chunk_id)
            if existing is None:
                by_chunk_id[chunk_id] = candidate
            else:
                if candidate.semantic_score is not None:
                    existing.semantic_score = candidate.semantic_score
                if candidate.lexical_score is not None:
                    existing.lexical_score = candidate.lexical_score
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank)

    ordered_ids = sorted(
        scores,
        key=lambda chunk_id: (
            -scores[chunk_id],
            by_chunk_id[chunk_id].chunk.id,
        ),
    )

    return [
        by_chunk_id[chunk_id]
        for chunk_id in ordered_ids[:top_k]
    ]


def candidate_to_result(candidate: RetrievalCandidate) -> RetrievalResult:
    chunk = candidate.chunk
    score = (
        candidate.semantic_score
        if candidate.semantic_score is not None
        else candidate.lexical_score or 0.0
    )
    return RetrievalResult(
        chunk_id=chunk.id,
        document_id=chunk.document_id,
        filename=candidate.filename,
        chunk_index=chunk.chunk_index,
        content=chunk.content,
        token_count=chunk.token_count,
        page_number=chunk.page_number,
        section_title=chunk.section_title,
        similarity_score=score,
    )


def retrieve_chunks(
    db: Session,
    user_id: int,
    query: str,
    top_k: int = DEFAULT_TOP_K,
    timings: RAGTimings | None = None,
) -> list[RetrievalResult]:

    query = query.strip()

    if not query:
        raise ValueError("Query cannot be empty.")

    if top_k <= 0:
        raise ValueError("top_k must be greater than 0.")

    fused_limit = rerank_candidate_limit(top_k)
    limit = branch_candidate_limit(fused_limit)
    if timings:
        with timings.measure("embedding"):
            query_embedding = embed_query(query)
    else:
        query_embedding = embed_query(query)

    if timings:
        with timings.measure("semantic"):
            semantic = semantic_candidates(
                db=db,
                user_id=user_id,
                query_embedding=query_embedding,
                limit=limit,
            )
        with timings.measure("lexical"):
            lexical = lexical_candidates(
                db=db,
                user_id=user_id,
                query=query,
                limit=limit,
            )
    else:
        semantic = semantic_candidates(
            db=db,
            user_id=user_id,
            query_embedding=query_embedding,
            limit=limit,
        )
        lexical = lexical_candidates(
            db=db,
            user_id=user_id,
            query=query,
            limit=limit,
        )

    if timings:
        with timings.measure("fusion"):
            fused = reciprocal_rank_fusion(
                semantic=semantic,
                lexical=lexical,
                top_k=fused_limit,
            )
    else:
        fused = reciprocal_rank_fusion(
            semantic=semantic,
            lexical=lexical,
            top_k=fused_limit,
        )

    if timings:
        with timings.measure("rerank"):
            reranked = rerank_candidates(
                query=query,
                candidates=fused,
                top_k=top_k,
            )
    else:
        reranked = rerank_candidates(
            query=query,
            candidates=fused,
            top_k=top_k,
        )

    return [
        candidate_to_result(candidate)
        for candidate in reranked
    ]
