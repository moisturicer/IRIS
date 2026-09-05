from pathlib import Path
from datetime import timedelta
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost").split(",")

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

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="iris_db"),
        "USER": config("DB_USER", default="iris_user"),
        "PASSWORD": config("DB_PASSWORD", default="iris_password"),
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

CORS_ALLOWED_ORIGINS = [FRONTEND_URL]
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

CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default="redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"

# ---- Static / Media -----------------------------------------------------

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ---- AI -----------------------------------------------------------------

AI_EMBEDDING_MODEL     = config("AI_EMBEDDING_MODEL", default="text-embedding-3-small")
AI_EMBEDDING_DIMENSIONS= config("AI_EMBEDDING_DIMENSIONS", default=1536, cast=int)
OPENAI_API_KEY         = config("OPENAI_API_KEY", default="")          # FR-M4: GPT-4.1-mini LLM inference + embedding API
ANTHROPIC_API_KEY      = config("ANTHROPIC_API_KEY", default="")       # Ask IRIS synthesis; unset -> retrieval-only mode
AI_LLM_MODEL           = config("AI_LLM_MODEL", default="claude-sonnet-5")
DOCLING_API_URL        = config("DOCLING_API_URL", default="http://localhost:5001")  # FR-M3-01: on-prem Docling-serve PDF extraction; Compose sets this to the service name
# A scanned thesis through OCR is minutes of work, not seconds. This bounds
# one conversion, not the Celery retry that wraps it.
DOCLING_TIMEOUT_SECONDS= config("DOCLING_TIMEOUT_SECONDS", default=600, cast=int)
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
# search. Front matter (acknowledgements, table of contents) is deliberately
# NOT excluded yet: whether the extractor detects those headings reliably on
# real submissions is one of the questions IR-116's manual inspection answers.
AI_CHUNK_EXCLUDE_SECTIONS = config(
    "AI_CHUNK_EXCLUDE_SECTIONS",
    default="References,Bibliography,Works Cited,Literature Cited",
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
