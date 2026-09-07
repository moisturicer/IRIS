FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (e.g. for asyncpg and curl for healthcheck)
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy the source into /app/ai/, NOT /app (IR-156).
#
# Every module here imports absolutely -- `from ai.api.chat import ...`,
# `from ai.domain.ports import ...` -- and `ai/tests/` does the same. Copying
# the build context's *contents* to /app left no `ai` package on sys.path, so
# `uvicorn main:app` failed at import even once the missing service modules
# existed. Preserving the package directory keeps one import convention across
# the container, the test suite and a local checkout.
COPY . ./ai/

# Run Uvicorn. Bind is 0.0.0.0 so the Compose network can reach it; the service
# publishes no port in either Compose file (ADR-014 precondition 2), so this
# does not expose it to the host.
CMD ["uvicorn", "ai.main:app", "--host", "0.0.0.0", "--port", "8001"]
