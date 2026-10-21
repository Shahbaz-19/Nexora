from datetime import datetime, timezone
import json
import re

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.chat import ChatMessage, ChatSession
from app.models.user import User
from app.rag.conversation import generate_conversation_answer
from app.schemas.chat import (
    ChatMessageResponse, ChatQueryRequest, ChatQueryResponse,
    ChatSessionDetail, ChatSessionResponse, ChatSourceResponse,
)

router = APIRouter(prefix="/chat", tags=["Chat"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


def stream_validated_response(response: ChatQueryResponse):
    """Progressively deliver only the already validated and persisted answer."""
    yield _sse("metadata", {
        "session_id": response.session_id,
        "session": response.session.model_dump(mode="json"),
        "user_message": response.user_message.model_dump(mode="json"),
    })
    for piece in re.findall(r"\S+\s*", response.answer):
        yield _sse("delta", {"content": piece})
    yield _sse("complete", response.model_dump(mode="json"))


def conversation_title(query: str) -> str:
    title = " ".join(query.split())
    if len(title) <= 80:
        return title
    prefix = title[:77]
    return (prefix.rsplit(" ", 1)[0] if " " in prefix else prefix) + "..."


def owned_session(db: Session, user_id: int, session_id: int, lock: bool = False) -> ChatSession:
    statement = select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id)
    if lock:
        # Serialize turns and deletion, including requests from other tabs.
        statement = statement.with_for_update()
    session = db.scalar(statement)
    if session is None:
        raise HTTPException(404, "Conversation not found.")
    return session


@router.post("/sessions", response_model=ChatSessionResponse, status_code=201)
def create_session(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = ChatSession(user_id=current_user.id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/sessions", response_model=list[ChatSessionResponse])
def list_sessions(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(ChatSession).where(ChatSession.user_id == current_user.id)
                      .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())).all()


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
def get_session(session_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return owned_session(db, current_user.id, session_id)


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(owned_session(db, current_user.id, session_id, lock=True))
    db.commit()
    return Response(status_code=204)


@router.post("/query", response_model=ChatQueryResponse)
def query_documents(request: ChatQueryRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = request.query.strip()
    if not query:
        raise HTTPException(422, "Query cannot be empty.")
    session = owned_session(db, current_user.id, request.session_id, lock=True) if request.session_id else ChatSession(user_id=current_user.id)
    db.add(session)
    try:
        db.flush()
        history = list(db.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.id)
        ).all())
        if not history:
            session.title = conversation_title(query)
        user_message = ChatMessage(session_id=session.id, role="USER", content=query, sources=[])
        db.add(user_message)
        db.flush()
        # Complete turns are atomic: generation failure rolls back the question too.
        result = generate_conversation_answer(
            db=db,
            user_id=current_user.id,
            query=query,
            history=history,
            top_k=request.top_k,
        )
        sources = [ChatSourceResponse(
            document_id=s.document_id, filename=s.filename, page_number=s.page_number,
            chunk_index=s.chunk_index, similarity_score=s.similarity_score,
        ).model_dump() for s in result.sources]
        assistant = ChatMessage(session_id=session.id, role="ASSISTANT", content=result.answer, sources=sources)
        db.add(assistant)
        session.updated_at = datetime.now(timezone.utc)
        db.flush()
        response = ChatQueryResponse(
            session_id=session.id, session=ChatSessionResponse.model_validate(session),
            user_message=ChatMessageResponse.model_validate(user_message),
            assistant_message=ChatMessageResponse.model_validate(assistant), answer=result.answer, sources=sources,
        )
        db.commit()
        return response
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, "Could not save an answer. Please try again.") from exc


@router.post("/query/stream")
def stream_query_documents(
    request: ChatQueryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    response = query_documents(request, current_user, db)
    return StreamingResponse(
        stream_validated_response(response),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
