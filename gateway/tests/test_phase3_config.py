"""Acceptance tests for the YAML plus environment configuration contract."""

from pathlib import Path

import pytest

from config import load_config


def write_config(path: Path) -> None:
    """Write a representative Phase 3 YAML configuration."""
    path.write_text(
        """
server:
  environment: production
  host: 127.0.0.2
  port: 9100
  log_level: WARNING
database:
  path: /tmp/from-yaml.db
auth:
  jwt_expiry_minutes: 20
  refresh_token_expiry_days: 9
  password_min_length: 10
ollama:
  base_url: http://yaml-ollama:11434
  timeout_seconds: 45
  max_retries: 4
audit_logging:
  retention_days: 120
  archive_path: /tmp/audit-archive
models:
  default_tier: default
  inference_queue_size: 1
""".strip(),
        encoding="utf-8",
    )


def test_yaml_configures_all_documented_runtime_sections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Server, database, auth, Ollama, and audit values load from YAML."""
    config_path = tmp_path / "config.yaml"
    write_config(config_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GATEWAY_ENV", raising=False)
    monkeypatch.delenv("GATEWAY_HOST", raising=False)
    monkeypatch.delenv("GATEWAY_PORT", raising=False)
    monkeypatch.delenv("GATEWAY_DB_PATH", raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("GATEWAY_LOG_AUDIT_RETENTION_DAYS", raising=False)
    monkeypatch.setenv("GATEWAY_JWT_SECRET", "x" * 40)

    loaded = load_config(config_path)

    assert loaded.gateway_env == "production"
    assert loaded.gateway_host == "127.0.0.2"
    assert loaded.gateway_port == 9100
    assert loaded.gateway_log_level == "WARNING"
    assert loaded.gateway_db_path == "/tmp/from-yaml.db"
    assert loaded.gateway_jwt_expiry_minutes == 20
    assert loaded.gateway_refresh_token_expiry_days == 9
    assert loaded.password_min_length == 10
    assert loaded.ollama_base_url == "http://yaml-ollama:11434"
    assert loaded.ollama_timeout_seconds == 45
    assert loaded.ollama_max_retries == 4
    assert loaded.audit_retention_days == 120
    assert loaded.audit_archive_path == "/tmp/audit-archive"


def test_environment_values_override_yaml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deployment environment values take precedence over YAML defaults."""
    config_path = tmp_path / "config.yaml"
    write_config(config_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GATEWAY_JWT_SECRET", "x" * 40)
    monkeypatch.setenv("GATEWAY_PORT", "9200")
    monkeypatch.setenv("GATEWAY_DB_PATH", "/tmp/from-env.db")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://env-ollama:11434")
    monkeypatch.setenv("GATEWAY_LOG_AUDIT_RETENTION_DAYS", "30")

    loaded = load_config(config_path)

    assert loaded.gateway_port == 9200
    assert loaded.gateway_db_path == "/tmp/from-env.db"
    assert loaded.ollama_base_url == "http://env-ollama:11434"
    assert loaded.audit_retention_days == 30


def test_default_runtime_ollama_url_targets_host_loopback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Phase 3 default runtime uses host Ollama, not a Compose service."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GATEWAY_JWT_SECRET", "x" * 40)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)

    loaded = load_config(tmp_path / "missing-config.yaml")

    assert loaded.ollama_base_url == "http://127.0.0.1:11434"
