from pydantic_settings import BaseSettings, SettingsConfigDict

class FrontendSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), env_ignore_empty=True, extra="ignore")
    backend_url: str = "http://localhost:8000"
    poll_interval_seconds: float = 2.0
    request_timeout_seconds: float = 120.0
