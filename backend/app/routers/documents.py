from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.config import settings
from app.database import get_db
from app.models.document import Document
from app.models.document import DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.models.user import User
from app.rag.ingestion import process_document_ingestion
from app.rag.parsers import SUPPORTED_EXTENSIONS
from app.schemas.document import (
    DocumentResponse,
    DocumentUploadResponse,
)


router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
)


MAX_FILE_SIZE = settings.max_upload_bytes


def document_response(
    document: Document,
    chunk_count: int,
) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        original_filename=document.original_filename,
        file_type=document.file_type,
        file_size=document.file_size,
        status=document.status,
        failure_reason=document.failure_reason,
        created_at=document.created_at,
        updated_at=document.updated_at,
        chunk_count=chunk_count,
    )


@router.get(
    "",
    response_model=list[DocumentResponse],
)
def list_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DocumentResponse]:

    statement = (
        select(
            Document,
            func.count(DocumentChunk.id).label("chunk_count"),
        )
        .outerjoin(
            DocumentChunk,
            DocumentChunk.document_id == Document.id,
        )
        .where(
            Document.user_id == current_user.id
        )
        .group_by(Document.id)
        .order_by(
            Document.created_at.desc()
        )
    )

    return [
        document_response(
            document=document,
            chunk_count=chunk_count,
        )
        for document, chunk_count in db.execute(statement).all()
    ]


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
)
def get_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentResponse:

    statement = (
        select(
            Document,
            func.count(DocumentChunk.id).label("chunk_count"),
        )
        .outerjoin(
            DocumentChunk,
            DocumentChunk.document_id == Document.id,
        )
        .where(
            Document.id == document_id,
            Document.user_id == current_user.id,
        )
        .group_by(Document.id)
    )

    row = db.execute(statement).one_or_none()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    document, chunk_count = row

    return document_response(
        document=document,
        chunk_count=chunk_count,
    )


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentUploadResponse:

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must have a filename.",
        )

    safe_filename = Path(
        file.filename
    ).name

    extension = Path(
        safe_filename
    ).suffix.lower()

    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                "Unsupported file type. "
                "Supported formats: PDF, TXT, MD."
            ),
        )

    try:
        file_bytes = file.file.read()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not read uploaded file.",
        ) from exc
    finally:
        file.file.close()

    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Maximum allowed file size is 10 MB.",
        )

    if (
        extension == ".pdf"
        and not file_bytes.startswith(b"%PDF-")
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is not a valid PDF.",
        )

    document = Document(
        user_id=current_user.id,
        original_filename=safe_filename,
        file_type=extension.lstrip("."),
        file_size=len(file_bytes),
        status=DocumentStatus.PROCESSING,
    )

    db.add(document)

    try:
        db.commit()
        db.refresh(document)
    except Exception as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create document record.",
        ) from exc

    background_tasks.add_task(
        process_document_ingestion,
        document.id,
        file_bytes,
    )

    return DocumentUploadResponse(
        id=document.id,
        original_filename=document.original_filename,
        file_type=document.file_type,
        file_size=document.file_size,
        status=document.status,
        failure_reason=document.failure_reason,
        created_at=document.created_at,
        updated_at=document.updated_at,
        chunk_count=0,
    )


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:

    statement = select(Document).where(
        Document.id == document_id,
        Document.user_id == current_user.id,
    )

    document = db.scalar(statement)

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    db.delete(document)
    db.commit()

    return Response(
        status_code=status.HTTP_204_NO_CONTENT
    )
