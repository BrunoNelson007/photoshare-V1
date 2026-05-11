from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "PhotoShare API"
    app_version: str = "1.0.0"
    debug: bool = False

    # Plain comma-separated string — avoids JSON parsing issues in Azure App Settings
    # Set ALLOWED_ORIGINS in Azure as: https://your-site.web.core.windows.net,http://localhost:3000
    allowed_origins: str = "https://photosharestorage.z28.web.core.windows.net"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    cosmos_endpoint: str
    cosmos_key: str
    cosmos_database: str = "photoshare"

    storage_connection_string: str
    storage_container: str = "photos"

    auth0_domain: str
    auth0_audience: str
    auth0_client_id: str
    auth0_client_secret: str

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
