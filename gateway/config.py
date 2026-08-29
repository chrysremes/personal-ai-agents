"""
Configuration loader for Agent Gateway
Merges environment variables and config.yaml
"""

from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from pathlib import Path
import yaml
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Main settings class - loads from .env and config.yaml"""
    
    # Server
    gateway_env: str = Field("development", alias="GATEWAY_ENV")
    gateway_host: str = Field("0.0.0.0", alias="GATEWAY_HOST")
    gateway_port: int = Field(8000, alias="GATEWAY_PORT")
    gateway_log_level: str = Field("INFO", alias="GATEWAY_LOG_LEVEL")
    
    # Database
    gateway_db_path: str = Field("/data/ai-platform/gateway.db", alias="GATEWAY_DB_PATH")
    
    # Authentication
    gateway_jwt_secret: str = Field("", alias="GATEWAY_JWT_SECRET")
    gateway_jwt_expiry_minutes: int = Field(15, alias="GATEWAY_JWT_EXPIRY_MINUTES")
    gateway_refresh_token_expiry_days: int = Field(7, alias="GATEWAY_REFRESH_TOKEN_EXPIRY_DAYS")
    
    # Ollama
    ollama_base_url: str = Field("http://ollama:11434", alias="OLLAMA_BASE_URL")
    
    # Claude
    claude_api_key: Optional[str] = Field(None, alias="CLAUDE_API_KEY")
    claude_api_endpoint: str = Field("https://api.anthropic.com/v1/messages", alias="CLAUDE_API_ENDPOINT")
    
    # Data Classification Patterns (from YAML)
    red_patterns: list = Field(default_factory=list)
    yellow_patterns: list = Field(default_factory=list)
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
    
    @field_validator("gateway_jwt_secret", mode="after")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        """Ensure JWT secret is set and reasonably long"""
        if not v or len(v) < 32:
            logger.warning("JWT secret is too short. Minimum 32 characters recommended.")
        return v


def load_config() -> Settings:
    """
    Load configuration from .env and config.yaml
    Environment variables override YAML values
    """
    settings = Settings()
    
    # Attempt to load YAML config (optional)
    config_yaml_path = Path("config.yaml")
    if config_yaml_path.exists():
        logger.info(f"Loading YAML config from {config_yaml_path}")
        try:
            with open(config_yaml_path, "r") as f:
                yaml_config = yaml.safe_load(f) or {}
            
            # Extract data classification patterns from YAML if present
            if "data_classification" in yaml_config:
                data_class_config = yaml_config.get("data_classification", {})
                settings.red_patterns = data_class_config.get("red_patterns", [])
                settings.yellow_patterns = data_class_config.get("yellow_patterns", [])
                logger.debug(f"Loaded RED patterns: {len(settings.red_patterns)}")
                logger.debug(f"Loaded YELLOW patterns: {len(settings.yellow_patterns)}")
            
            logger.debug(f"YAML config sections: {list(yaml_config.keys())}")
        except Exception as e:
            logger.warning(f"Failed to load YAML config: {e}")
    else:
        logger.debug("No config.yaml found, using .env only")
    
    # Validate required fields
    if not settings.gateway_jwt_secret or len(settings.gateway_jwt_secret) < 32:
        raise ValueError(
            "GATEWAY_JWT_SECRET environment variable is required and must be at least 32 characters"
        )
    
    logger.info(
        f"Configuration loaded: env={settings.gateway_env}, "
        f"db={settings.gateway_db_path}, "
        f"host={settings.gateway_host}:{settings.gateway_port}"
    )
    return settings


# Global settings instance
try:
    settings = load_config()
except Exception as e:
    logger.error(f"Configuration error: {e}")
    raise

