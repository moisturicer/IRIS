from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # App Config
    APP_NAME: str = "IRIS AI Gateway"
    DEBUG: bool = False

    # AI Configuration
    # 'openai' or 'local'
    LLM_PROVIDER: str = "openai"
    EMBEDDING_PROVIDER: str = "openai"
    
    # Provider-specific settings
    OPENAI_API_KEY: str = ""
    LOCAL_LLM_URL: str = "http://localhost:11434" # Example for Ollama
    
    # Models
    LLM_MODEL: str = "gpt-4o-mini"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
