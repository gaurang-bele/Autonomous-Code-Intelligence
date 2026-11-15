from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    github_token: str = ""
    openai_api_key: str = ""
    github_api_url: str = "https://api.github.com"
    llm_model: str = "gpt-4o-mini"
    llm_provider: str = "openai"
    checkpoint_db: str = "data/checkpoints.sqlite"
    sandbox_timeout_seconds: int = 15
    max_file_size_bytes: int = 500000
    github_webhook_secret: str = ""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

@lru_cache
def get_settings():
    return Settings()
