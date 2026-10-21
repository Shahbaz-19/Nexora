from pydantic import BaseModel, Field


class RetrievalRequest(BaseModel):
    query: str = Field(
        min_length=1,
        max_length=2000,
    )

    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
    )


class RetrievalResultResponse(BaseModel):
    chunk_id: int
    document_id: int
    filename: str
    chunk_index: int
    content: str
    token_count: int
    page_number: int | None
    section_title: str | None
    similarity_score: float


class RetrievalResponse(BaseModel):
    query: str
    results: list[RetrievalResultResponse]