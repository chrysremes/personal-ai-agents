"""Typed configuration loading with environment-over-YAML precedence."""

from pathlib import Path
import logging
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml

logger = logging.getLogger(__name__)


class ServerYaml(BaseModel):
    """Server defaults loaded from YAML."""

    environment: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1
    debug: bool = False
    log_level: str = "INFO"


class DatabaseYaml(BaseModel):
    """Database defaults loaded from YAML."""

    path: str = "/data/ai-platform/gateway.db"


class AuthYaml(BaseModel):
    """Authentication defaults loaded from YAML."""

    jwt_expiry_minutes: int = 15
    refresh_token_expiry_days: int = 7
    password_min_length: int = 8


class OllamaYaml(BaseModel):
    """Ollama defaults loaded from YAML."""

    base_url: str = "http://127.0.0.1:11434"
    timeout_seconds: int = 120
    max_retries: int = 3
    retry_backoff_ms: list[int] = Field(default_factory=lambda: [1000, 2000, 4000])


class ModelTierYaml(BaseModel):
    """One model tier and its optional timeout."""

    models: list[str] = Field(default_factory=list)
    timeout_seconds: Optional[int] = None


class ModelsYaml(BaseModel):
    """Model routing and queue defaults loaded from YAML."""

    default_tier: str = "default"
    inference_queue_size: int = 1
    tiers: dict[str, ModelTierYaml] = Field(default_factory=dict)


class ClassificationYaml(BaseModel):
    """Named RED and YELLOW pattern definitions."""

    red_patterns: list[Any] = Field(default_factory=list)
    yellow_patterns: list[Any] = Field(default_factory=list)


class AuditYaml(BaseModel):
    """Audit retention and archive defaults loaded from YAML."""

    retention_days: int = 90
    archive_path: str = "/data/ai-platform/backups/audit-logs"


class YamlConfig(BaseModel):
    """Validated shape of config.yaml."""

    server: ServerYaml = Field(default_factory=ServerYaml)
    database: DatabaseYaml = Field(default_factory=DatabaseYaml)
    auth: AuthYaml = Field(default_factory=AuthYaml)
    ollama: OllamaYaml = Field(default_factory=OllamaYaml)
    models: ModelsYaml = Field(default_factory=ModelsYaml)
    data_classification: ClassificationYaml = Field(default_factory=ClassificationYaml)
    audit_logging: AuditYaml = Field(default_factory=AuditYaml)


class Settings(BaseSettings):
    """Runtime settings sourced from environment variables and typed YAML."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        populate_by_name=True,
        extra="ignore",
    )

    gateway_env: str = Field("development", alias="GATEWAY_ENV")
    gateway_host: str = Field("0.0.0.0", alias="GATEWAY_HOST")
    gateway_port: int = Field(8000, alias="GATEWAY_PORT")
    gateway_workers: int = Field(1, alias="GATEWAY_WORKERS")
    gateway_debug: bool = Field(False, alias="GATEWAY_DEBUG")
    gateway_log_level: str = Field("INFO", alias="GATEWAY_LOG_LEVEL")
    gateway_db_path: str = Field("/data/ai-platform/gateway.db", alias="GATEWAY_DB_PATH")

    gateway_jwt_secret: str = Field("", alias="GATEWAY_JWT_SECRET")
    gateway_jwt_algorithm: str = Field("HS256", alias="GATEWAY_JWT_ALGORITHM")
    gateway_jwt_expiry_minutes: int = Field(15, alias="GATEWAY_JWT_EXPIRY_MINUTES")
    gateway_refresh_token_expiry_days: int = Field(7, alias="GATEWAY_REFRESH_TOKEN_EXPIRY_DAYS")
    password_min_length: int = Field(8, alias="GATEWAY_PASSWORD_MIN_LENGTH")

    ollama_base_url: str = Field("http://127.0.0.1:11434", alias="OLLAMA_BASE_URL")
    ollama_timeout_seconds: int = Field(120, alias="OLLAMA_TIMEOUT_SECONDS")
    ollama_max_retries: int = Field(3, alias="OLLAMA_MAX_RETRIES")
    ollama_retry_backoff_ms: list[int] = Field(default_factory=lambda: [1000, 2000, 4000])
    inference_timeouts_by_model: Dict[str, int] = Field(default_factory=dict)
    default_model_tier: str = "default"
    inference_queue_size: int = 1

    claude_api_key: Optional[str] = Field(None, alias="CLAUDE_API_KEY")
    claude_api_endpoint: str = Field(
        "https://api.anthropic.com/v1/messages",
        alias="CLAUDE_API_ENDPOINT",
    )

    audit_retention_days: int = Field(90, alias="GATEWAY_LOG_AUDIT_RETENTION_DAYS")
    audit_archive_path: str = Field(
        "/data/ai-platform/backups/audit-logs",
        alias="GATEWAY_AUDIT_ARCHIVE_PATH",
    )
    red_patterns: list[Any] = Field(default_factory=list)
    yellow_patterns: list[Any] = Field(default_factory=list)

    @field_validator("gateway_jwt_secret", mode="after")
    @classmethod
    def validate_jwt_secret(cls, value: str) -> str:
        if not value or len(value) < 32:
            logger.warning("JWT secret is too short. Minimum 32 characters required.")
        return value


def _flatten_yaml(config: YamlConfig) -> dict[str, Any]:
    """Translate nested YAML sections into runtime setting names."""
    timeouts = {
        model_name: tier.timeout_seconds
        for tier in config.models.tiers.values()
        if tier.timeout_seconds is not None
        for model_name in tier.models
    }
    return {
        "gateway_env": config.server.environment,
        "gateway_host": config.server.host,
        "gateway_port": config.server.port,
        "gateway_workers": config.server.workers,
        "gateway_debug": config.server.debug,
        "gateway_log_level": config.server.log_level,
        "gateway_db_path": config.database.path,
        "gateway_jwt_expiry_minutes": config.auth.jwt_expiry_minutes,
        "gateway_refresh_token_expiry_days": config.auth.refresh_token_expiry_days,
        "password_min_length": config.auth.password_min_length,
        "ollama_base_url": config.ollama.base_url,
        "ollama_timeout_seconds": config.ollama.timeout_seconds,
        "ollama_max_retries": config.ollama.max_retries,
        "ollama_retry_backoff_ms": config.ollama.retry_backoff_ms,
        "default_model_tier": config.models.default_tier,
        "inference_queue_size": config.models.inference_queue_size,
        "inference_timeouts_by_model": timeouts,
        "red_patterns": config.data_classification.red_patterns,
        "yellow_patterns": config.data_classification.yellow_patterns,
        "audit_retention_days": config.audit_logging.retention_days,
        "audit_archive_path": config.audit_logging.archive_path,
    }


def load_config(config_yaml_path: Optional[Path] = None) -> Settings:
    """Load YAML defaults while retaining environment and .env overrides."""
    runtime_settings = Settings()
    yaml_path = config_yaml_path or Path(__file__).with_name("config.yaml")

    if yaml_path.exists():
        logger.info("Loading YAML config from %s", yaml_path)
        with yaml_path.open("r", encoding="utf-8") as config_file:
            yaml_config = YamlConfig.model_validate(yaml.safe_load(config_file) or {})

        environment_fields = runtime_settings.model_fields_set
        for field_name, value in _flatten_yaml(yaml_config).items():
            if field_name not in environment_fields:
                setattr(runtime_settings, field_name, value)

    if len(runtime_settings.gateway_jwt_secret) < 32:
        raise ValueError(
            "GATEWAY_JWT_SECRET environment variable is required and must be at least 32 characters"
        )

    logger.info(
        "Configuration loaded: env=%s, db=%s, host=%s:%s",
        runtime_settings.gateway_env,
        runtime_settings.gateway_db_path,
        runtime_settings.gateway_host,
        runtime_settings.gateway_port,
    )
    return runtime_settings


settings = load_config()
