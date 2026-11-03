# Build from repository root. This image has no Django application or ORM.
FROM python:3.12-slim
WORKDIR /app
COPY ai/requirements.txt ai/requirements.txt
COPY ai/ingestion/requirements.txt ai/ingestion/requirements.txt
RUN pip install --no-cache-dir -r ai/ingestion/requirements.txt
COPY ai /app/ai
COPY backend/apps/ai/chunking /app/apps/ai/chunking
COPY backend/apps/ai/extraction /app/apps/ai/extraction
USER 65534:65534
ENTRYPOINT ["python", "-m", "ai.ingestion.extract_worker"]
