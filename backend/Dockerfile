FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HOME=/models/huggingface
WORKDIR /app

ARG REQUIREMENTS_FILE=requirements-cloud.txt
COPY requirements*.txt ./
RUN pip install --no-cache-dir -r ${REQUIREMENTS_FILE}
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

EXPOSE 8000
CMD ["sh", "-c", "python -m app.db_bootstrap && alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
