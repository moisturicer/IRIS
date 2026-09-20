from pathlib import Path
from datetime import timedelta

from decouple import UndefinedValueError, config
from django.core.exceptions import ImproperlyConfigured

from .validation import missing_required, non_blank

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def csv_list(value):
    """A comma-separated environment variable as a list, blanks dropped.

    ``"".split(",")`` is ``[""]`` — one blank entry, which reads as configured
    everywhere it is checked for emptiness. Everything list-shaped here goes
    through this instead.
    """
    return list(non_blank(str(value).split(",")))


def required(name, cast=str):
    """Read a mandatory setting, or refuse to start (IR-154).

    CLAUDE.md's Environment and secrets rule: the app fails to start on a
    missing required secret rather than defaulting silently. A default is what
    turns a forgotten variable into a deployment running on the credential that
    was committed to the repository — which is the bug this ticket exists to
    close, not a convenience worth keeping.
    """
    try:
        value = config(name, cast=cast)
    except UndefinedValueError:
        value = None

    if missing_required({name: value}):
        raise ImproperlyConfigured(
            f"{name} is not set. It has no default: see backend/.env.example "
            "for every variable this deployment must supply."
        )
    return value


SECRET_KEY = required("SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost", cast=csv_list)

# ---- Apps ---------------------------------------------------------------

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",  # for SearchVectorField
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "axes",
    "pgvector",
]

LOCAL_APPS = [
    "apps.accounts",
    "apps.records",
    "apps.reviews",
    "apps.documents",
    "apps.notifications",
    "apps.audit",
    "apps.ai",
    "apps.opportunities",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ---- Middleware ----------------------------------------------------------

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---- Database -----------------------------------------------------------

# The three credential components have no defaults on purpose (IR-154). The
# defaults they replace were credential literals in the repository, and they
# were live: both Compose files provisioned Postgres with exactly those
# values, so a deployment that forgot to set them did not fail — it connected.
# HOST and PORT keep defaults because neither is a credential and
# localhost:5432 is the right guess when running outside Compose.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": required("DB_NAME"),
        "USER": required("DB_USER"),
        "PASSWORD": required("DB_PASSWORD"),
        "HOST": config("DB_HOST", default="localhost"),
        "PORT": config("DB_PORT", default="5432"),
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---- Auth ---------------------------------------------------------------

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---- REST Framework -----------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "core.pagination.StandardResultsPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/day",
        "user": "1000/day",
        "ai_query": "60/hour",
    },
}

# ---- JWT ----------------------------------------------------------------

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=config("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", default=30, cast=int)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=config("JWT_REFRESH_TOKEN_LIFETIME_DAYS", default=7, cast=int)
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# ---- CORS ---------------------------------------------------------------

FRONTEND_URL = config("FRONTEND_URL", default="http://localhost:5173")

# An explicit allowlist, always — there is no "allow all" switch in any
# settings module, and production.py refuses to start if one reappears.
# CORS_ALLOW_CREDENTIALS below is why: with credentials enabled, a wildcard
# origin lets any site make authenticated requests on a logged-in user's
# behalf. Defaults to the single configured frontend origin; set
# CORS_ALLOWED_ORIGINS when a deployment serves more than one.
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS", default=FRONTEND_URL, cast=csv_list
)
CORS_ALLOW_CREDENTIALS = True

# ---- Email --------------------------------------------------------------

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = config("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

# ---- Celery -------------------------------------------------------------

# Both Compose files have set REDIS_URL on every backend service since the
# stack was written, and until IR-132 nothing in Django read it -- the same
# shape as the EXTRACTION_TIMEOUT the compose comments record as declared and
# unread. The rate limiter needs a raw client (atomic INCR plus an expiry,
# which django.core.cache cannot express), so it is a real setting now.
REDIS_URL = config("REDIS_URL", default="redis://localhost:6379/0")

CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default="redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"

# IR-164: without this, every task publishes to Celery's own implicit
# "celery" queue, which none of docker-compose.yml's three workers consume
# (they run `-Q default` / `-Q extraction` / `-Q embedding`) -- so nothing
# dispatched is ever picked up. CELERY_TASK_DEFAULT_QUEUE catches any task
# with no explicit route below, present or future, and lands it on the
# worker with no special dependencies. Tasks with a real dependency (a
# Docling container, the embedding vendor) are routed to the workers built
# for them.
#
# IR-240: `default` is the safe fallback for a task that needs nothing, and
# the wrong one for a task that needs Docling -- `celery-default` is not
# given DOCLING_API_URL, so an unrouted extractor task falls back to
# http://localhost:5001 and fails against its own container. That is what
# happened to extract_manuscript_text between IR-195 and IR-240, and it
# broke the manuscript path in every Docker deployment while the test suite
# stayed green, because the tasks are tested against a fake extractor with
# no queue involved. **Every task that reaches an extractor belongs on
# `extraction`** -- apps/ai/tests/test_celery_routing.py now derives that
# set from the source and enforces it, rather than trusting this list to be
# kept in step by hand.
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_ROUTES = {
    "apps.documents.tasks.extract_pdf_text": {"queue": "extraction"},
    "apps.documents.tasks.extract_manuscript_text": {"queue": "extraction"},
    "apps.ai.tasks.embed_record": {"queue": "embedding"},
    "apps.ai.tasks.embed_chunk_set": {"queue": "embedding"},
    "apps.ai.tasks.index_record": {"queue": "embedding"},
}

# ---- Static / Media -----------------------------------------------------

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ---- Workflow (ADR-002, ADR-004, ADR-005) --------------------------------

# The per-instance workflow table. `apps.records.lifecycle.load_table()` reads
# `STAGES` and `TRANSITIONS` from here; both are absent by default, so CIT-U's
# table in that module is used unchanged.
#
# `RESUBMISSION_POLICY` is ADR-004's experimental control (IR-137):
# `clearance_aware` preserves every non-declining office's completed review and
# is the contribution; `restart_all` resets them all, and exists so the claim
# can be measured against something instead of asserted.
#
# **This is deployment configuration and must stay that way.** ADR-004 makes it
# a hard operational rule: the comparison arm runs on a dedicated, short-lived
# evaluation instance, never on a customer's production one, because a policy
# that resets clearances would destroy live reviewers' completed work. It has no
# endpoint and no serializer field, and `apps/records/test_lifecycle.py` fails
# if any module outside a short allowlist so much as names it.
#
# The value is validated by `RecordsConfig.ready()`, so an unrecognised one
# stops the app at startup instead of defaulting — a silent fallback would run
# the evaluation on the production arm and say nothing. The spec's own upper-case
# spelling (`RESTART_ALL`) is accepted.
WORKFLOW_TABLE = {
    "RESUBMISSION_POLICY": config("RESUBMISSION_POLICY", default="clearance_aware"),
}

# ---- Logging -------------------------------------------------------------

# Until IR-137 there was no LOGGING at all, so the root logger sat at its
# default WARNING with no handlers and every `logger.info` in `apps/` was
# discarded. That made ADR-004's "record which policy was active for each
# evaluation run" false in practice: the line was written and thrown away.
#
# Deliberately minimal. Root stays at WARNING so Django's own noise is
# unchanged; only `apps.*` is lifted to INFO, and `disable_existing_loggers`
# is False so Django's default loggers survive. `apps/records/test_lifecycle.py`
# asserts INFO really is enabled, because this failing silently is exactly how
# it went unnoticed the first time.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"},
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "apps": {
            "handlers": ["console"],
            "level": config("APP_LOG_LEVEL", default="INFO"),
            "propagate": False,
        },
    },
}

# ---- AI -----------------------------------------------------------------

# ---- Cache (IR-132) ------------------------------------------------------
#
# Absent until now: Celery and Redis were configured, but Django itself had no
# CACHES at all, so `django.core.cache` fell back to the local-memory backend
# -- per process. That is the same defect the rate limiter is built to avoid:
# correct with one process, wrong with four.
#
# Django 5 ships a Redis backend, so this needs no extra dependency. The same
# Redis as Celery, on a different database number, so flushing a queue cannot
# take the query-embedding cache with it.
REDIS_CACHE_URL = config("REDIS_CACHE_URL", default="redis://localhost:6379/1")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_CACHE_URL,
        "KEY_PREFIX": "iris",
        # A query embedding is valid for as long as the embedding space is,
        # which is far longer than a day -- but an unbounded cache is a slow
        # memory leak, and the space id is in the key, so an expired entry is
        # recomputed rather than wrong.
        "TIMEOUT": config("CACHE_TIMEOUT_SECONDS", default=86_400, cast=int),
    }
}

# The vendor account's per-minute token budget, divided between the ingestion
# and query lanes by `apps.ai.resilience.rate_limit`. The query lane is given
# the larger share because a person is waiting on it (ADR-015).
AI_RATE_LIMIT_TOKENS_PER_MINUTE = config(
    "AI_RATE_LIMIT_TOKENS_PER_MINUTE", default=1_000_000, cast=int
)

# ---- Inference provider (ADR-021) ---------------------------------------
#
# Groq in development, OpenRouter in production, and the switch is these three
# values -- no second adapter. Every vendor worth using here speaks the OpenAI
# chat-completions format, so `OpenAICompatibleAdapter` covers Groq,
# OpenRouter, OpenAI, Together, vLLM and Ollama alike.
#
# Anthropic is deliberately absent: it was chosen in an import statement rather
# than a decision record, was never declared as a dependency, and silently
# degraded every environment to extractive answers. ADR-021 supersedes it.
#
# No default key and no local fallback -- the adapter raises rather than
# degrading to a mock, which is the failure ADR-021 records the previous
# provider factory for.
LLM_BASE_URL  = config("LLM_BASE_URL", default="https://api.groq.com/openai/v1")
LLM_API_KEY   = config("LLM_API_KEY", default="")
LLM_MODEL     = config("LLM_MODEL", default="openai/gpt-oss-120b")
# Grounded answering is extraction from supplied sources, not composition. A
# higher temperature buys variety nobody asked for and invites invention.
LLM_TEMPERATURE = config("LLM_TEMPERATURE", default=0.1, cast=float)

# ---- Voyage (ADR-015, IR-128) -------------------------------------------
#
# One vendor for both stages, embedding and reranking, with no alternative in
# scope. `voyage-context-4` is a *contextualized* chunk embedder: it sees a
# chunk's neighbours, which is why ADR-015 notes it may reduce the need for
# the context-path prefix on the embedded string specifically.
#
# The key has no default and no local fallback -- ADR-008 rejected a local
# model and ADR-015's short-lived local lane was removed the same day for
# contradicting it. `VoyageEmbeddingProvider` therefore raises when the key is
# absent rather than degrading silently.
#
# Deliberately *not* wired into `required()` or `production_problems()`: the
# query lane that consumes Voyage is not built yet (IR-129 onward), and a
# start-up check would break every deployment and CI job that does not use
# RAG. The start-up assertion belongs with the switch that turns the query
# lane on, not with the adapter.
VOYAGE_API_KEY         = config("VOYAGE_API_KEY", default="")
VOYAGE_EMBED_MODEL     = config("VOYAGE_EMBED_MODEL", default="voyage-context-4")
# VOYAGE_EMBED_DIMENSIONS was removed by IR-280. The dimension Voyage is asked
# to emit and the width of the column that stores it are one number, and two
# settings for one number is the drift this ticket closed everywhere else:
# `VOYAGE_EMBED_DIMENSIONS=512` would have produced 512-vectors for a 1024
# column. The adapter now takes it from `apps.ai.models.VECTOR_COLUMN_DIMENSIONS`,
# which a migration ties to the active `EmbeddingSpace` row.
VOYAGE_RERANK_MODEL    = config("VOYAGE_RERANK_MODEL", default="rerank-3")
VOYAGE_TIMEOUT_SECONDS = config("VOYAGE_TIMEOUT_SECONDS", default=60, cast=int)

# ---- Embedding spend (IR-282) -------------------------------------------
#
# Indexing is metered per token, and `AI_CHUNK_MAX_TOKENS` counts whitespace
# words rather than tokenizer tokens — about 44% under the real BPE count
# (IR-243, deliberately not recalibrated ahead of IR-133's evidence). A
# misconfigured ceiling therefore turns one corpus run into a large bill
# quietly, which is the failure this pair of settings exists to bound.
#
# The ceiling is a refusal, not a warning: `backfill_embeddings` prints its
# estimate and stops when the estimate exceeds this, and raising it is a
# deliberate act by whoever is paying. 0 disables the guard.
AI_EMBEDDING_TOKEN_CEILING = config(
    "AI_EMBEDDING_TOKEN_CEILING", default=2_000_000, cast=int
)
# Approximate, and printed as approximate. Vendor pricing is not in this
# repository's control, so this is a figure for deciding whether a run is
# worth starting, never a quote. Voyage's contextualized-embedding list price
# at the time of writing; check it before trusting a large number.
#
# Corrected 2026-09-20: was 0.18, verified against Voyage's published pricing
# page during a live cost-verification session -- voyage-context-4 lists at
# 0.12/M tokens, not 0.18. The stale figure had been overstating every dry-run
# estimate by 50%, in the direction of caution rather than the dangerous one,
# but a pre-flight number that is wrong on the safe side is still wrong.
AI_EMBEDDING_COST_PER_MILLION_TOKENS = config(
    "AI_EMBEDDING_COST_PER_MILLION_TOKENS", default=0.12, cast=float
)

# AI_EMBEDDING_MODEL and AI_EMBEDDING_DIMENSIONS were removed by IR-280. They
# named a second embedding model and dimension alongside the VOYAGE_EMBED_*
# family above, and the three declarations disagreed: 1536 here, 1024 there,
# and `all-MiniLM-L6-v2` in .env.example. `voyage-context-4` emits 2048, 1024,
# 512 or 256 and never 1536, so the vector columns those settings sized could
# not have held a real vector. What produced a vector is now the active
# `EmbeddingSpace` row (ADR-015); what the columns are wide enough for is
# `apps.ai.models.VECTOR_COLUMN_DIMENSIONS`, which a migration and a test tie
# to that row.
OPENAI_API_KEY         = config("OPENAI_API_KEY", default="")          # FR-M4: GPT-4.1-mini LLM inference + embedding API
# ANTHROPIC_API_KEY and AI_LLM_MODEL were removed by ADR-021. Anthropic is not
# used, and a setting nothing reads is the defect this codebase keeps finding
# (REDIS_URL in IR-132, EXTRACTION_TIMEOUT in the compose comments). The
# inference provider is configured by LLM_BASE_URL / LLM_API_KEY / LLM_MODEL
# above.
DOCLING_API_URL        = config("DOCLING_API_URL", default="http://localhost:5001")  # FR-M3-01: on-prem Docling-serve PDF extraction; Compose sets this to the service name
# A scanned thesis through OCR is minutes of work, not seconds. This bounds
# one conversion, not the Celery retry that wraps it.
DOCLING_TIMEOUT_SECONDS= config("DOCLING_TIMEOUT_SECONDS", default=600, cast=int)
# Nothing in Django reads this any more (IR-281). ADR-024 took the indexing
# path off the gateway — it posted to a route the gateway never registered, at
# an endpoint returning no vector field — and Django now embeds in-process
# through the `EmbeddingProvider` port. The setting stays because ADR-014
# keeps the service for its streaming-chat mandate, which is still gated on
# that ADR's preconditions plus ADR-017's ASGI deployment.
AI_GATEWAY_URL         = config("AI_GATEWAY_URL", default="http://ai-gateway:8001") # AI Gateway endpoint

# ---- Chunking (ADR-013) --------------------------------------------------
#
# The knobs the ingestion pipeline builds its ChunkingOptions from. They are
# configuration rather than constants because IR-116's exit criterion is a
# person reading fifty real chunks and choosing the ceiling from what they
# see — so changing it must be a deployment decision, not a code change.
#
# Blank means the domain's own DEFAULT_STRATEGY, resolved in
# apps.ai.ingestion.pipeline. Naming it here would put a third copy of the
# strategy id in the tree -- and this is the copy that could silently drift
# from the registry, because a settings module must not import an app
# package to check itself against it.
AI_CHUNK_STRATEGY      = config("AI_CHUNK_STRATEGY", default="")
# NOTE THE UNIT: whitespace-delimited *words*, not tokenizer tokens
# (apps.ai.chunking.tokens.count_tokens). Measured against docling-core's
# HybridChunker on the same PDF, 512 words is ~44% more real BPE tokens than
# "512" suggests -- the equivalent of that reference default is nearer 360.
# Nothing overflows (voyage-context-4 has the context for it), so IR-243
# deliberately left the number alone: what the right ceiling is for theses is
# a retrieval-quality question for IR-133's recall@10 harness, not a guess.
AI_CHUNK_MAX_TOKENS    = config("AI_CHUNK_MAX_TOKENS", default=512, cast=int)
# Blank means "derive from max_tokens" — see ChunkingOptions.effective_min_tokens,
# which explains why a fixed default would be a footgun.
AI_CHUNK_MIN_TOKENS    = config(
    "AI_CHUNK_MIN_TOKENS", default="", cast=lambda v: int(v) if str(v).strip() else None
)
AI_CHUNK_CONTEXT_PATH_MAX_TOKENS = config(
    "AI_CHUNK_CONTEXT_PATH_MAX_TOKENS", default=48, cast=int
)
# A bibliography is 10-20% of a thesis by tokens and retrieves uniformly
# badly, so it is excluded here and kept in extracted_text for full-text
# search.
#
# The navigation indexes join it as of IR-246. IR-116's run on two real CIT-U
# submissions answered the open question this comment used to pose: Docling
# does emit a real `Table of Contents` heading, so these are detectable by
# name. They earn exclusion on the same grounds as a bibliography and then
# some -- a table of contents holds every section name in the document and
# none of their content, so it scores against a query about any section and
# returns a page number. On record 30 it ranked within 0.005 of the correct
# answer for "user characteristics and constraints".
#
# The title block is deliberately still chunked: institution, title and
# authors are the document's identity, which is the one part of front matter
# worth retrieving. Acknowledgements are still undecided -- neither test
# submission had one, and guessing is what this list is trying to stop.
AI_CHUNK_EXCLUDE_SECTIONS = config(
    "AI_CHUNK_EXCLUDE_SECTIONS",
    default=(
        "References,Bibliography,Works Cited,Literature Cited,"
        "Table of Contents,Contents,List of Tables,List of Figures"
    ),
    cast=lambda v: tuple(s.strip() for s in str(v).split(",") if s.strip()),
)

# ---- Axes (brute force protection) --------------------------------------

AXES_FAILURE_LIMIT = config("AXES_FAILURE_LIMIT", default=3, cast=int)
AXES_LOCK_OUT_BY_COMBINATION_USER_AND_IP = True
AXES_RESET_ON_SUCCESS = True
AXES_COOLOFF_TIME = timedelta(
    minutes=config("AXES_COOLOFF_TIME_MINUTES", default=10, cast=int)
)

# ---- Internationalisation -----------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Manila"
USE_I18N = True
USE_TZ = True

# TODO: configure django-storages for S3 in production
# TODO: configure Sentry in production settings
