from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_name: str = "PhotoShare API"
    app_version: str = "1.0.0"
    debug: bool = False
    allowed_origins: list[str] = ["https://your-staticwebapp.azurestaticapps.net"]

    # Azure Cosmos DB
    cosmos_endpoint: str
    cosmos_key: str
    cosmos_database: str = "photoshare"

    # Azure Blob Storage
    storage_connection_string: str
    storage_container: str = "photos"

    # Auth0 (JWT validation) — free tier: 25,000 MAUs
    # replaces Azure AD B2C which no longer has a free tier
    auth0_domain: str         # e.g. "your-tenant.auth0.com"
    auth0_audience: str       # e.g. "https://photoshare-api"
    auth0_client_id: str      # SPA client ID (used by frontend)

    # Azure Computer Vision
    vision_endpoint: str
    vision_key: str

    # Azure Language (Sentiment)
    language_endpoint: str
    language_key: str

    # Azure Key Vault (optional - for production secret retrieval)
    key_vault_url: str = ""

    # Security
    rate_limit_per_minute: int = 60
    max_upload_size_mb: int = 10

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
