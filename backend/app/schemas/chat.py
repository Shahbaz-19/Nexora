from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class ChatQueryRequest(BaseModel):
    session_id: int | None = Field(default=None, gt=0)
    query: str = Field(
        min_length=1,
        max_length=2000,
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=10,
    )


class ChatSourceResponse(BaseModel):
    document_id: int
    filename: str
    page_number: int | None
    chunk_index: int
    similarity_score: float


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    role: Literal["USER", "ASSISTANT"]
    content: str
    sources: list[ChatSourceResponse]
    created_at: datetime


class ChatSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    created_at: datetime
    updated_at: datetime


class ChatSessionDetail(ChatSessionResponse):
    messages: list[ChatMessageResponse]


class ChatQueryResponse(BaseModel):
    session_id: int
    session: ChatSessionResponse
    user_message: ChatMessageResponse
    assistant_message: ChatMessageResponse
    answer: str
    sources: list[ChatSourceResponse]
