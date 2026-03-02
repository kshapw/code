import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    llm_base_url: str = os.getenv("LLM_BASE_URL", "http://ollama:11434/v1")
    llm_api_key: str = os.getenv("LLM_API_KEY", "ollama")
    llm_model: str = os.getenv("LLM_MODEL", "sqlcoder")
    llm_temperature: float = 0.0
    cors_origins: str = os.getenv("CORS_ORIGINS", "*")
    debug: bool = False

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
