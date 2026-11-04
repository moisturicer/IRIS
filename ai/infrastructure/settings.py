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
    # only `python -m ai.runs.migrate` may hold (ADR-014, IR-826).
    RUNS_DATABASE_URL: str = ""
    RUNS_MIGRATION_DATABASE_URL: str = ""
    # What new runs are pinned to: "deterministic", or "agent", which needs
    # the whole AGENT profile below and refuses to start without it (IR-862).
    RUNS_EXECUTOR: str = "deterministic"
    # The AGENT profile (IR-862). No defaults: the model AGENT runs are pinned
    # to, per-depth Bounds and the context Reserves, as JSON.
    RUNS_AGENT_MODEL: str = ""
    RUNS_AGENT_BOUNDS: str = ""
    RUNS_AGENT_RESERVES: str = ""
    # No defaults: unset limits refuse every submission.
    RUNS_DEADLINE_SECONDS: int | None = None
    RUNS_LEASE_SECONDS: int | None = None
    RUNS_MAX_ATTEMPTS: int | None = None
    RUNS_MAX_INPUT_TOKENS: int | None = None
    RUNS_MAX_OUTPUT_TOKENS: int | None = None
    RUNS_MAX_COST_USD: float | None = None
    # Dispatch (IR-723); also required, none approved.
    RUNS_DEEP_DEADLINE_SECONDS: int | None = None
    RUNS_MAX_QUEUED: int | None = None
    RUNS_MAX_ACTIVE_PER_READER: int | None = None
    RUNS_MAX_RUNNING_PER_READER: int | None = None
    RUNS_DEEP_CONCURRENCY: int | None = None
    RUNS_WORKER_CONCURRENCY: int | None = None
    RUNS_POLL_SECONDS: float | None = None
    # Worker wakeups only; empty means workers poll PostgreSQL.
    RUNS_REDIS_URL: str = ""
    # Provider admission (IR-725): Django's names, one shared campaign.
    # No defaults; unset refuses every paid attempt.
    AI_ADMISSION_CAMPAIGN: str = ""
    AI_ADMISSION_CAMPAIGN_MAX_ATTEMPTS: str = ""
    AI_ADMISSION_CAMPAIGN_MAX_INPUT_TOKENS: str = ""
    AI_ADMISSION_CAMPAIGN_MAX_OUTPUT_TOKENS: str = ""
    AI_ADMISSION_CAMPAIGN_MAX_COST_USD: str = ""
    AI_ADMISSION_CAMPAIGN_MAX_ACTIVE_MINUTES: str = ""
    AI_ADMISSION_RESERVE_FRACTION: str = ""
    AI_ADMISSION_RESERVE_RELEASED: str = ""
    AI_ADMISSION_LANE_CONCURRENCY: str = ""
    AI_ADMISSION_ACCOUNT_CONCURRENCY: str = ""
    AI_ADMISSION_PRICES: str = ""
    AI_ADMISSION_MAX_OUTPUT_TOKENS: str = ""
    AI_ADMISSION_LEASE_GRACE_SECONDS: str = ""
    # The chat-completions AGENT provider (IR-860). Read by
    # `ai.infrastructure.agent_config`; no defaults, and capacity is declared
    # per model in AGENT_LLM_CAPACITIES, never inferred.
    AGENT_LLM_ENDPOINT: str = ""
    AGENT_LLM_API_KEY: str = ""
    AGENT_LLM_MODELS: str = ""
    AGENT_LLM_CAPABILITIES: str = ""
    AGENT_LLM_DATA_POLICY: str = ""
    AGENT_LLM_CAPACITIES: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
