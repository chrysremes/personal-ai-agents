"""Acceptance tests for MCP tool and operational status endpoints."""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from db import SessionLocal, reset_db
from main import app
from models import AuditLog
import main


@pytest.fixture
def client() -> TestClient:
    reset_db()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def authenticated_client(client: TestClient) -> tuple[TestClient, dict[str, str]]:
    setup = client.post(
        "/admin/setup/user",
        json={"username": "owner", "password": "SecurePass1!"},
    )
    assert setup.status_code == 200
    login = client.post(
        "/auth/login",
        json={"username": "owner", "password": "SecurePass1!"},
    )
    token = login.json()["access_token"]
    return client, {"Authorization": f"Bearer {token}"}


def test_tool_listing_requires_authentication(client: TestClient) -> None:
    assert client.get("/tools").status_code == 401


def test_tool_listing_returns_registered_schemas(
    authenticated_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, headers = authenticated_client

    response = client.get("/tools", headers=headers)

    assert response.status_code == 200
    tools = {tool["name"]: tool for tool in response.json()["tools"]}
    assert "google_calendar.list_events" in tools
    assert tools["google_calendar.list_events"]["arguments"]["date_range"] == {
        "type": "string",
        "required": True,
    }


def test_registered_stub_tool_validates_calls_and_is_audited(
    authenticated_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, headers = authenticated_client

    response = client.post(
        "/tools/google_calendar.list_events",
        headers=headers,
        json={"arguments": {"date_range": "next 7 days"}},
    )

    assert response.status_code == 200
    assert response.json()["tool"] == "google_calendar.list_events"
    assert response.json()["status"] == "success"
    db = SessionLocal()
    event = db.query(AuditLog).filter(AuditLog.action == "request_tool").one()
    db.close()
    assert event.result == "success"


@pytest.mark.parametrize(
    "payload",
    [
        {"arguments": {}},
        {"arguments": {"date_range": 7}},
        {"arguments": {"date_range": "tomorrow", "unknown": True}},
    ],
)
def test_tool_argument_validation_rejects_invalid_payloads(
    authenticated_client: tuple[TestClient, dict[str, str]],
    payload: dict,
) -> None:
    client, headers = authenticated_client

    response = client.post(
        "/tools/google_calendar.list_events",
        headers=headers,
        json=payload,
    )

    assert response.status_code == 400


def test_unknown_tool_returns_not_found(
    authenticated_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, headers = authenticated_client

    response = client.post(
        "/tools/missing.tool",
        headers=headers,
        json={"arguments": {}},
    )

    assert response.status_code == 404


def test_health_reports_database_ollama_and_queue_state(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main.ollama_provider, "health_check", AsyncMock(return_value=True))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "database": "connected",
        "ollama": "connected",
        "queue_depth": 0,
    }


def test_health_is_degraded_when_ollama_is_unavailable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main.ollama_provider, "health_check", AsyncMock(return_value=False))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["ollama"] == "unavailable"


def test_status_requires_authentication(client: TestClient) -> None:
    assert client.get("/status").status_code == 401


def test_status_reports_phase_models_sessions_uptime_and_queue(
    authenticated_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, headers = authenticated_client

    response = client.get("/status", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["phase"] == 3
    assert body["gateway_version"] == app.version
    assert body["uptime_seconds"] >= 0
    assert "qwen3.5:2b" in body["models_available"]
    assert body["active_sessions"] == 1
    assert body["queue_depth"] == 0
