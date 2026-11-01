from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # App Config
    APP_NAME: str = "IRIS AI Gateway"
    DEBUG: bool = False

    # AI Configuration
    LLM_PROVIDER: str = "openai"
    # No EMBEDDING_PROVIDER switch: IRIS has exactly one embedding provider
    # (ADR-015). A second switch here, independent of Django's, is how the
    # two ends of the pipeline could silently disagree about what produced a
    # vector — get_embedding_provider() below constructs the one adapter
    # directly instead.

    # Service-to-service authentication (ADR-014 precondition 1, IR-156).
    # Shared with Django, which sends it as the x-iris-service-secret
    # header. Empty by default, and the gateway then refuses every request
    # with 503: a service holding a vendor API key must not serve anyone
    # who can reach the port, and shipping a default value would make an
    # unconfigured deployment look configured.
    SERVICE_SECRET: str = ""

    # Provider-specific settings
    OPENAI_API_KEY: str = ""

    # Models
    LLM_MODEL: str = "gpt-4o-mini"
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # AI-owned runs (IR-722). The runtime login, and the maintenance login
    # `python -m ai.runs.migrate` uses.
    RUNS_DATABASE_URL: str = ""
    RUNS_MIGRATION_DATABASE_URL: str = ""
    # Only the deterministic executor exists; no paid work is possible.
    RUNS_EXECUTOR: str = "deterministic"
    # No defaults: unset limits refuse every submission.
    RUNS_DEADLINE_SECONDS: int | None = None
    RUNS_LEASE_SECONDS: int | None = None
    RUNS_MAX_ATTEMPTS: int | None = None
    RUNS_MAX_INPUT_TOKENS: int | None = None
    RUNS_MAX_OUTPUT_TOKENS: int | None = None
    RUNS_MAX_COST_USD: float | None = None
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
