# Nexora

**Intelligence, connected.**

Nexora is an AI-Powered Knowledge Intelligence Platform built with FastAPI, Next.js, PostgreSQL/pgvector, configurable Gemini or local Nomic embeddings, PostgreSQL full-text search, RRF, an optional local cross-encoder reranker, and Groq structured generation.

## Features

- Secure email/password authentication with short-lived JWT access tokens, rotating refresh sessions, and HttpOnly cookies.
- Per-user document ingestion for PDF, TXT, and Markdown files with asynchronous parsing, chunking, and embedding.
- Hybrid retrieval through pgvector semantic search, PostgreSQL full-text search, Reciprocal Rank Fusion, and optional local reranking.
- Persistent, conversation-aware chat with follow-up rewriting and bounded history.
- Backend-validated structured provenance, trusted source cards, and clearly separated supplemental guidance.
- Knowledge Base management for upload status, document metadata, and deletion.
- Responsive Next.js interface with validated progressive SSE delivery.

## Repository layout

| Path | Purpose |
| --- | --- |
| `backend/app` | FastAPI routes, authentication, ingestion, retrieval, generation, and persistence |
| `backend/alembic` | PostgreSQL and pgvector schema migrations |
| `backend/evaluation` | Versioned deterministic RAG evaluation cases |
| `backend/test_*.py` | Backend unit and integration tests |
| `frontend/src` | Next.js App Router application and shared UI components |
| `frontend/tests` | Browser-level Playwright tests |
| `docker-compose.yml` | Local full-stack environment with pgvector PostgreSQL |
| `render.yaml` | Render backend service configuration |

## Architecture

Uploads are validated and accepted with `202`, then parsed, chunked, embedded, and indexed by an in-process FastAPI background task. Retrieval is scoped to the authenticated user, READY documents, and the active embedding provider/model identity. Semantic and lexical candidates are fused with RRF, optionally reranked locally, and sent to Groq. The backend validates structured provenance before persisting and returning answers.

`POST /chat/query/stream` uses SSE. Generation and provenance validation finish before delivery begins; the validated Markdown is then emitted progressively and the final event contains trusted source metadata. This adds perceived streaming while preventing unvalidated model output from reaching clients.

## Local setup

1. Create `backend/.env` from `.env.example`, changing the database host to `localhost` when PostgreSQL runs outside Docker.
2. Create and activate a Python 3.11 virtual environment in `backend`.
3. Install dependencies: `pip install -r requirements.txt`.
4. Apply migrations: `alembic upgrade head`.
5. Start the API: `uvicorn app.main:app --reload`.
6. In `frontend`, run `npm ci` and `npm run dev`.

The frontend is available at `http://localhost:3000` and the API at `http://localhost:8000`. API documentation is available at `http://localhost:8000/docs` in development.

`.env.example` selects `nomic_local` plus the local reranker for local development. To use hosted embeddings locally, set `EMBEDDING_PROVIDER=gemini`, provide `GEMINI_API_KEY`, and set `RERANKER_PROVIDER=none`.

## Docker

Copy `.env.example` to `.env`, replace every placeholder secret, then run:

```powershell
docker compose build
docker compose up -d
docker compose ps
docker compose logs -f backend
```

The backend applies Alembic migrations before starting. Local Compose explicitly builds `requirements.txt`, which includes the local ML dependencies, and persists the Hugging Face cache. The cloud Dockerfile default installs `requirements-cloud.txt` without PyTorch or sentence-transformers.

Stop the stack with `docker compose down`. Add `-v` only when you intentionally want to delete database and model-cache volumes.

## Configuration

Required: `DATABASE_URL`, `JWT_SECRET_KEY`, `GROQ_API_KEY`, `GROQ_MODEL`, and `POSTGRES_PASSWORD` for Compose. `GEMINI_API_KEY` is required only for `EMBEDDING_PROVIDER=gemini`. Embedding settings include `GEMINI_EMBEDDING_MODEL`, `EMBEDDING_REQUEST_TIMEOUT_SECONDS`, and `EMBEDDING_BATCH_SIZE`. `RERANKER_PROVIDER` accepts `none` or `local`. `NEXT_PUBLIC_API_URL` is compiled into the frontend image.

Production HTTPS deployments should use `COOKIE_SECURE=true`. Cross-site frontend/API deployments also require `COOKIE_SAMESITE=none`; same-site deployments should retain `lax`. CORS origins must be explicit.

## Vercel + Render + Neon deployment

### Measured model constraint

Run `python scripts/profile_model_memory.py` from `backend` to reproduce the model memory profile. On the current Windows development machine, one fresh Python process measured:

| Stage | Resident memory |
| --- | ---: |
| Process baseline | 15 MiB |
| ML imports | 380 MiB |
| Nomic loaded and warmed | 922 MiB |
| Nomic + cross-encoder loaded and warmed | 1,022 MiB |

These measurements rule out the local model stack on Render Free. Cloud configuration instead uses `gemini-embedding-001` at 768 dimensions and disables the cross-encoder, retaining RRF ranking. The cloud app does not import or warm PyTorch. Gemini free-tier availability and limits depend on the Google project and are not guaranteed; check the active quota in Google AI Studio before deployment.

Gemini uses `RETRIEVAL_DOCUMENT` for chunks and `RETRIEVAL_QUERY` for queries. The backend requests 768 dimensions, manually L2-normalizes the result as required for reduced `gemini-embedding-001` vectors, and rejects wrong-length, zero, NaN, or infinite vectors. The official SDK handles configured timeouts and bounded retry/backoff for 408, 429, and transient 5xx responses.

### Embedding-space migration

Nomic and Gemini vectors are incompatible despite both having 768 values. Migration `f2c31a8bd420` records `embedding_provider` and `embedding_model` on every document and marks pre-existing vectors as Nomic. Both semantic and lexical retrieval require an exact match with the active identity, so legacy documents cannot leak into Gemini retrieval.

After changing the environment to Gemini and applying migrations, re-index existing READY documents explicitly from `backend`:

```powershell
.\venv\Scripts\python.exe -m alembic upgrade head
.\venv\Scripts\python.exe -m app.rag.reindex --all --yes
```

For selected documents:

```powershell
.\venv\Scripts\python.exe -m app.rag.reindex --document-id 12 --document-id 27 --yes
```

The command embeds stored chunk text before acquiring row locks. It then verifies the document and every chunk are unchanged and replaces all vectors plus the provider/model identity in one transaction. API, quota, validation, or concurrency failures leave the previous vectors and identity intact. It never runs during application startup. Use `--force` only when intentionally regenerating documents already using the active identity.

### Neon

1. Create a Neon project and copy its **pooled** connection string.
2. Set Render `DATABASE_URL` to the connection string and retain `sslmode=require`. Both `postgresql://` and `postgresql+psycopg://` are accepted; the application normalizes the former to psycopg v3.
3. Keep the small default pool (`DATABASE_POOL_SIZE=3`, `DATABASE_MAX_OVERFLOW=2`) for Neon's pooled endpoint.
4. The container runs `python -m app.db_bootstrap` to enable `vector`, followed by `alembic upgrade head`, before Uvicorn starts. The Neon role must be allowed to create the supported `vector` extension.

Migration `f2c31a8bd420` adds embedding identity and its retrieval index. Check migration state with `alembic current` and `alembic heads`.

### Render backend

Create the service from `render.yaml`, or configure a Docker web service with root directory left at the repository root and `backend/Dockerfile`. Set the secret values from `backend/.env.render.example`:

- `DATABASE_URL`: Neon pooled URL with `sslmode=require`
- `JWT_SECRET_KEY`: a random value of at least 32 bytes
- `GROQ_API_KEY`: server-side only
- `GEMINI_API_KEY`: server-side only
- `CORS_ORIGINS`: the exact production Vercel origin, with no trailing slash

Render uses `/health` and the container honors its injected `PORT`. The default cloud image uses `requirements-cloud.txt`; it has no local embedding or reranking weights. Do not put secrets in Docker build arguments. Free services spin down when idle, and in-process document background tasks can be interrupted by restarts.

### Vercel frontend

Import the repository and set **Root Directory** to `frontend`. `frontend/vercel.json` uses `npm ci` and `npm run build`. Add `NEXT_PUBLIC_API_URL=https://your-render-service.onrender.com` for Production (and separately for Preview if used), then redeploy because public variables are compiled into the browser bundle.

The browser sends the refresh cookie directly to Render. Set `COOKIE_SECURE=true` and `COOKIE_SAMESITE=none`, and keep `allow_credentials` with exact CORS origins. Some browsers or privacy modes block cross-site cookies even with these attributes. Custom domains under one registrable domain (for example `app.example.com` and `api.example.com`) avoid that third-party-cookie dependency and allow `COOKIE_SAMESITE=lax`.

For preview deployments, either list the exact preview origins or set a tightly anchored `CORS_ORIGIN_REGEX`; never use `*` with credentialed requests.

## Tests

From `backend`:

```powershell
.\venv\Scripts\python.exe -m compileall app
.\venv\Scripts\python.exe -m unittest discover -p "test_*.py" -v
```

From `frontend`:

```powershell
npm run lint
npm run build
npx playwright test
```

Live external-service integration tests are opt-in through the environment variables documented in `backend/test_chat_history.py`. Unit tests mock Gemini and do not consume quota.

## RAG evaluation

`backend/evaluation/cases.json` is a small versioned evaluation set with answerable, unanswerable, and follow-up cases. `app/evaluation.py` provides deterministic Recall@K, expected-fact, and citation-validity helpers. Run `python -m unittest test_evaluation -v` for deterministic metrics. Live answer evaluation must use a known uploaded corpus and should report raw results; no benchmark score is bundled or claimed.

## Known limitations

- FastAPI background tasks are not durable. A restart loses queued file bytes; stale PROCESSING rows are marked FAILED at startup and users must upload those documents again.
- Validated progressive delivery begins after Groq completes, so it improves presentation rather than time to first validated answer.
- SSE requests already committed before delivery remain in chat history if the browser disconnects; clients reconcile from the stored conversation.
- Gemini embedding free-tier capacity, geography, and rate limits may change. A real key/quota call and a full document re-index were not exercised by unit tests.
- Disabling the local reranker reduces model memory substantially but returns RRF ordering without cross-encoder refinement.
- Production still needs TLS termination, managed secrets, backups, centralized logs/metrics, alerting, rate limiting at the gateway, and CI/CD.
