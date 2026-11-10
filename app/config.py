from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    azure_openai_endpoint: str
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_chat_deployment: str = "chat"  # deployment name (gpt-4.1-mini)
    azure_openai_embedding_deployment: str = "text-embedding-3-small"
    azure_search_endpoint: str
    azure_search_index: str = "docs"
    # Optional keys. If set, used instead of Entra/DefaultAzureCredential (lab convenience).
    azure_openai_api_key: str | None = None
    azure_search_api_key: str | None = None
    # Semantic reranker score is 0-4. Below this = "not grounded" -> skip LLM (saves tokens).
    min_rerank_score: float = 1.0
    max_output_tokens: int = 400


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
