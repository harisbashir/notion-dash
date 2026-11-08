from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    notion_token: SecretStr
    ds_projects: str
    ds_ai_todos: str
    ds_my_tasks: str
    ds_ideas: str
    ds_ai_notes: str
    ds_my_notes: str
    cache_ttl_seconds: int = 30
    timezone: str = "America/Toronto"
    owner_name: str = "Haris"


@lru_cache
def get_settings() -> Settings:
    return Settings()
