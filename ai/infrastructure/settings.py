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

    # Provider-specific settings
    OPENAI_API_KEY: str = ""

    # Models
    LLM_MODEL: str = "gpt-4o-mini"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
