# Backend Dockerfile
# Uses a multi-stage build so the final image stays small.
# Stage 1: build dependencies (includes gcc for psycopg2)
# Stage 2: runtime image

# ------ builder ------
FROM python:3.12-slim AS builder

WORKDIR /build

# System deps needed to compile psycopg2 and Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev libjpeg-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/base.txt requirements/base.txt
COPY requirements/production.txt requirements/production.txt
COPY requirements/development.txt requirements/development.txt

ARG REQUIREMENT_FILE=production.txt

# Install into a local prefix so we can COPY it to the runtime stage
RUN pip install --prefix=/install --no-cache-dir \
    -r requirements/${REQUIREMENT_FILE}

# ------ runtime ------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production

WORKDIR /app

# Runtime system libs only (no gcc)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 libjpeg62-turbo \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY . .

# Create a non-root user and change ownership of the app directory
RUN useradd -m appuser && chown -R appuser:appuser /app

# Switch to the non-root user
USER appuser

# Collect static files (WhiteNoise will serve them)
# TODO: run this during CI/CD, not at image build time in production
RUN python manage.py collectstatic --noinput

EXPOSE 8000

# Production entry point -- gunicorn
# TODO: switch to uvicorn if async views are added
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "120"]
