from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.core.exceptions import ConfigurationError

DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
DEFAULT_BEDROCK_MODEL = "anthropic.claude-opus-5-5"
CONVERSE_PROFILE_PREFIXES = ("us.", "eu.", "apac.", "jp.", "au.", "global.", "arn:")
DEFAULT_JEV_MODEL = "jev-latest"

class FitWeights(BaseModel):
    must_have_requirements: float = 0.40
    nice_to_have_requirements: float = 0.10
    fit_dimensions: float = 0.30
    seniority: float = 0.12
    ats_alignment: float = 0.08
    max_red_flag_penalty: float = 0.20

class DimensionWeights(BaseModel):
    technical: float = 0.35
    domain: float = 0.20
    tools: float = 0.30
    soft_skills: float = 0.15

class ValidationThresholds(BaseModel):
    requirement_met: float = 0.70
    requirement_partial: float = 0.40
    claim_supported: float = 0.60
    red_flag_triggered: float = 0.60
    low_confidence: float = 0.50
    keyword_present: float = 0.50
    quality_noul_pass: float = 0.60
    quality_score_pass: float = 0.60
    min_ats_improvement: float = 0.01

class RecommendationThresholds(BaseModel):
    apply_score: float = 72.0
    skip_score: float = 45.0
    apply_min_must_have_coverage: float = 0.85
    skip_max_must_have_coverage: float = 0.50
    apply_min_ats: float = 0.65

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        env_nested_delimiter="__",
        extra="ignore",
    )
    typesafe_api_key: SecretStr = SecretStr("")
    typesafe_default_model: str = DEFAULT_JEV_MODEL
    typesafe_base_url: str | None = None
    llm_provider: Literal["bedrock", "groq"] = "bedrock"
    llm_schema_retries: int = Field(default=3, ge=1, le=6)
    llm_timeout_seconds: float = 300.0
    llm_max_tokens: int = Field(default=16000, ge=1024, le=64000)
    aws_bearer_token_bedrock: SecretStr = SecretStr("")
    bedrock_region: str = "us-east-1"
    bedrock_model_id: str = DEFAULT_BEDROCK_MODEL
    bedrock_base_url: str | None = None
    bedrock_api: Literal["auto", "messages", "converse"] = "auto"
    bedrock_temperature: float | None = None
    groq_api_key: SecretStr = SecretStr("")
    groq_model: str = DEFAULT_GROQ_MODEL
    groq_extraction_temperature: float = 0.0
    groq_chat_temperature: float = 0.4
    backend_url: str = "http://localhost:8000"
    frontend_origins: str = "http://localhost:8501,http://127.0.0.1:8501"
    max_agent_iterations: int = Field(default=6, ge=1, le=20)
    max_agent_steps_per_iteration: int = Field(default=4, ge=2, le=10)
    max_agent_nudges: int = Field(default=2, ge=0, le=5)
    max_tool_errors: int = Field(default=3, ge=1, le=10)
    max_concurrent_jobs: int = Field(default=3, ge=1, le=10)
    enable_web_search: bool = True
    web_search_max_results: int = Field(default=5, ge=1, le=10)
    session_storage: Literal["memory", "file"] = "memory"
    session_storage_path: Path = Path("data/sessions")
    session_ttl_minutes: int = Field(default=120, ge=1)
    session_cleanup_interval_seconds: int = Field(default=300, ge=10)
    max_upload_bytes: int = 5 * 1024 * 1024
    max_request_bytes: int = 12 * 1024 * 1024
    max_jobs_per_session: int = Field(default=10, ge=1, le=50)
    chat_history_window: int = Field(default=20, ge=2, le=100)
    chat_max_tool_rounds: int = Field(default=3, ge=1, le=6)
    jev_max_questions_per_call: int = Field(default=40, ge=1, le=200)
    jev_max_state_chars: int = Field(default=60000, ge=2000)
    jev_max_concurrent_calls: int = Field(default=8, ge=1, le=64)
    jev_timeout_seconds: float = 30.0
    jev_max_retries: int = Field(default=3, ge=0, le=10)
    http_fetch_timeout_seconds: float = 15.0
    respect_robots_txt: bool = True
    min_job_text_chars: int = 300
    min_pasted_job_chars: int = 80
    max_job_text_chars: int = 30000
    max_source_text_chars: int = 40000
    max_cv_words: int = 900
    max_bullets_per_role: int = 6
    log_level: str = "INFO"
    fit_weights: FitWeights = FitWeights()
    dimension_weights: DimensionWeights = DimensionWeights()
    thresholds: ValidationThresholds = ValidationThresholds()
    recommendation_thresholds: RecommendationThresholds = RecommendationThresholds()

    @field_validator("groq_model", "bedrock_model_id", "bedrock_region", "typesafe_default_model", mode="before")
    @classmethod
    def strip_model_name(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origins.split(",") if origin.strip()]

    @property
    def llm_model(self) -> str:
        if self.llm_provider == "groq":
            return self.groq_model
        return self.bedrock_converse_model_id if self.uses_bedrock_converse else self.bedrock_model_id

    @property
    def bedrock_endpoint(self) -> str:
        return self.bedrock_base_url or f"https://bedrock-mantle.{self.bedrock_region}.api.aws/anthropic"

    @property
    def uses_bedrock_converse(self) -> bool:
        if self.bedrock_api != "auto":
            return self.bedrock_api == "converse"
        model_id = self.bedrock_model_id
        return ":" in model_id or model_id.startswith(CONVERSE_PROFILE_PREFIXES)

    @property
    def bedrock_converse_model_id(self) -> str:
        model_id = self.bedrock_model_id
        if model_id.startswith(CONVERSE_PROFILE_PREFIXES):
            return model_id
        geography = "us" if self.bedrock_region.startswith(("us-", "ca-")) else "eu" if self.bedrock_region.startswith("eu-") else "global"
        return f"{geography}.{model_id}"

    @property
    def max_agent_steps(self) -> int:
        return self.max_agent_iterations * self.max_agent_steps_per_iteration + 8

    def missing_required_keys(self) -> list[str]:
        llm_key = ("AWS_BEARER_TOKEN_BEDROCK", self.aws_bearer_token_bedrock) if self.llm_provider == "bedrock" else ("GROQ_API_KEY", self.groq_api_key)
        required = {"TYPESAFE_API_KEY": self.typesafe_api_key, llm_key[0]: llm_key[1]}
        return [name for name, value in required.items() if not value.get_secret_value().strip()]

class SettingsLoader:
    def load(self) -> Settings:
        try:
            settings = Settings()
        except ValidationError as error:
            raise ConfigurationError(f"Invalid configuration in .env: {error.errors()[0].get('msg', 'unknown error')}") from error
        missing = settings.missing_required_keys()
        if missing:
            raise ConfigurationError(
                f"Missing required configuration: {', '.join(missing)}. Copy .env.example to .env and fill in the keys."
            )
        return settings
