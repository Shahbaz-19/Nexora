from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.rag.retrieval import retrieve_chunks
from app.schemas.retrieval import (
    RetrievalRequest,
    RetrievalResponse,
    RetrievalResultResponse,
)


router = APIRouter(
    prefix="/retrieval",
    tags=["Retrieval"],
)


@router.post(
    "/search",
    response_model=RetrievalResponse,
)
def search_documents(
    request: RetrievalRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RetrievalResponse:

    query = request.query.strip()

    if not query:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Query cannot be empty.",
        )

    try:
        results = retrieve_chunks(
            db=db,
            user_id=current_user.id,
            query=query,
            top_k=request.top_k,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Document retrieval failed.",
        ) from exc

    return RetrievalResponse(
        query=query,
        results=[
            RetrievalResultResponse(
                chunk_id=result.chunk_id,
                document_id=result.document_id,
                filename=result.filename,
                chunk_index=result.chunk_index,
                content=result.content,
                token_count=result.token_count,
                page_number=result.page_number,
                section_title=result.section_title,
                similarity_score=result.similarity_score,
            )
            for result in results
        ],
    )