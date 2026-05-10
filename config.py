from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "PhotoShare API"
    app_version: str = "1.0.0"
    debug: bool = False
    allowed_origins: list[str] = ["https://photosharestorage.z28.web.core.windows.net"]

    cosmos_endpoint: str
    cosmos_key: str
    cosmos_database: str = "photoshare"

    storage_connection_string: str
    storage_container: str = "photos"

    auth0_domain: str
    auth0_audience: str
    auth0_client_id: str

    vision_endpoint: str
    vision_key: str

    language_endpoint: str
    language_key: str

    rate_limit_per_minute: int = 60
    max_upload_size_mb: int = 10

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
