# app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Server
    port: int = 8000
    env: str = "development"

    # Database
    database_url: str

    # Google OAuth2
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str

    # Session
    session_secret_key: str

    # App
    app_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:5173"

    @property
    def is_production(self) -> bool:
        return self.env == "production"


settings = Settings()  # type: ignore[call-arg]