import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import update

from app.core.config import settings
from app.database import SessionLocal
from app.models.document import Document, DocumentStatus
from app.rag.embeddings import active_embedding_description, warm_up_embedding_model
from app.rag.reranker import RERANKER_MODEL_NAME, warm_up_reranker_model
from app.routers.auth import router as auth_router
from app.routers.chat import router as chat_router
from app.routers.documents import router as documents_router
from app.routers.retrieval import router as retrieval_router


logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    with SessionLocal() as db:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.stale_processing_minutes)
        db.execute(
            update(Document)
            .where(Document.status == DocumentStatus.PROCESSING, Document.updated_at < cutoff)
            .values(
                status=DocumentStatus.FAILED,
                failure_reason="Processing was interrupted by an application restart. Upload the document again.",
            )
        )
        db.commit()
    if settings.embedding_provider == "nomic_local":
        logger.info("Loading local embedding model at startup: %s", active_embedding_description())
        elapsed = warm_up_embedding_model()
        logger.info("Embedding model ready | load_time=%sms", round(elapsed * 1000))
    else:
        logger.info("Hosted embedding provider configured: %s", active_embedding_description())
    if settings.reranker_provider == "local":
        logger.info("Loading reranker model at startup: %s", RERANKER_MODEL_NAME)
        reranker_elapsed = warm_up_reranker_model()
        logger.info(
            "Reranker model ready | model=%s | load_time=%sms",
            RERANKER_MODEL_NAME,
            round(reranker_elapsed * 1000),
        )
    else:
        logger.info("Local reranker disabled; using RRF ordering.")
    yield


app = FastAPI(
    title="Nexora API",
    version="0.1.0",
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(retrieval_router)
app.include_router(chat_router)


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "Nexora",
    }
