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

# Create a non-root user and change ownership of the app directory.
# media/ is explicitly created (not just left to Django's first FileField
# save) because docker-compose.yml mounts it as a *named volume*
# (media_files:/app/media) — Docker initializes a named volume empty and
# root-owned, then populates it by copying the image's directory at that
# path on first mount. Without a media/ directory existing here, owned by
# appuser, that first mount stays root-owned and every upload gets
# "PermissionError: [Errno 13] Permission denied" the first time anything
# writes to it (found via the Submit Disclosure manuscript upload, IR-88).
RUN useradd -m appuser && mkdir -p /app/media && chown -R appuser:appuser /app

# Switch to the non-root user
USER appuser

# Collect static files (WhiteNoise will serve them)
# TODO: run this during CI/CD, not at image build time in production
#
# The DB_* values are build-time throwaways and are never baked into the image:
# they exist only for the lifetime of this RUN. `collectstatic` does not touch
# the database -- it needs them purely because importing settings does, since
# IR-154 made DB_NAME/DB_USER/DB_PASSWORD `required()` with no defaults. Before
# that, the defaults it removed were quietly satisfying this line, so dropping
# them broke the image build (IR-198) while every CI job stayed green, because
# CI validates the compose files and never builds.
#
# Do NOT "simplify" this by restoring defaults in settings. The whole point of
# IR-154 is that a deployment missing a real credential fails loudly instead of
# connecting to something it guessed.
# The full set is exactly six: SECRET_KEY, DB_NAME, DB_USER and DB_PASSWORD from
# base.py, plus ALLOWED_HOSTS and CORS_ALLOWED_ORIGINS, which production.py adds.
# Every one is a throwaway that lives only for this RUN. Enumerating them keeps
# the image built against the *real* production settings path rather than
# quietly switching to development settings for the build -- and the static
# output is identical either way, since STATIC_ROOT and the WhiteNoise storage
# both live in base.py.
RUN SECRET_KEY=build-time-only \
    DB_NAME=build-time-only \
    DB_USER=build-time-only \
    DB_PASSWORD=build-time-only \
    ALLOWED_HOSTS=localhost \
    CORS_ALLOWED_ORIGINS=http://localhost \
    python manage.py collectstatic --noinput

EXPOSE 8000

# Production entry point -- gunicorn
# ASGI, per ADR-017 (IR-156). Django calls the AI gateway over HTTP;
# under sync WSGI workers that call blocks one of only four workers for
# the whole duration of a model round trip, so four concurrent questions
# stall every other request in the system. config/asgi.py already exists.
CMD ["gunicorn", "config.asgi:application", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "120"]
