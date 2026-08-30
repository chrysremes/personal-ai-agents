"""End-to-end HTTP acceptance tests for the Phase 3 gateway flows."""

from datetime import datetime, timedelta, timezone
import time
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from auth import password_manager
from db import SessionLocal, reset_db
from main import app
from models import AuditLog, RefreshToken, User
import routes_chat


@pytest.fixture
def client() -> TestClient:
    """Provide an initialized, isolated gateway application."""
    reset_db()
    with TestClient(app) as test_client:
        yield test_client


def create_login(client: TestClient, username: str = "owner") -> dict[str, str]:
    """Create the initial user and return its login token payload."""
    setup = client.post(
        "/admin/setup/user",
        json={"username": username, "password": "SecurePass1!"},
    )
    assert setup.status_code == 200
    login = client.post(
        "/auth/login",
        json={"username": username, "password": "SecurePass1!"},
    )
    assert login.status_code == 200
    return login.json()


def auth_header(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def test_setup_user_is_exposed_at_the_specified_public_url(client: TestClient) -> None:
    response = client.post(
        "/admin/setup/user",
        json={"username": "owner", "password": "SecurePass1!"},
    )

    assert response.status_code == 200
    assert client.post(
        "/auth/admin/setup/user",
        json={"username": "other", "password": "SecurePass1!"},
    ).status_code == 404


@pytest.mark.parametrize(
    "username",
    ["ab", "a" * 33, "owner name", "owner!"],
)
def test_setup_rejects_usernames_outside_the_documented_contract(
    client: TestClient,
    username: str,
) -> None:
    response = client.post(
        "/admin/setup/user",
        json={"username": username, "password": "SecurePass1!"},
    )

    assert response.status_code == 422


def test_setup_is_disabled_after_the_first_user(client: TestClient) -> None:
    create_login(client)

    response = client.post(
        "/admin/setup/user",
        json={"username": "other", "password": "SecurePass1!"},
    )

    assert response.status_code == 403


def test_valid_login_returns_access_and_refresh_tokens(client: TestClient) -> None:
    tokens = create_login(client)

    assert tokens["token_type"] == "bearer"
    assert tokens["expires_in"] == 900
    assert tokens["access_token"]
    assert len(tokens["refresh_token"]) == 64


def test_login_rejects_an_unknown_user(client: TestClient) -> None:
    response = client.post(
        "/auth/login",
        json={"username": "missing", "password": "SecurePass1!"},
    )

    assert response.status_code == 401


def test_login_rejects_an_invalid_password(client: TestClient) -> None:
    create_login(client)

    response = client.post(
        "/auth/login",
        json={"username": "owner", "password": "WrongPass1!"},
    )

    assert response.status_code == 401


def test_login_rejects_an_inactive_user(client: TestClient) -> None:
    create_login(client)
    db = SessionLocal()
    db.query(User).filter(User.username == "owner").update({User.is_active: False})
    db.commit()
    db.close()

    response = client.post(
        "/auth/login",
        json={"username": "owner", "password": "SecurePass1!"},
    )

    assert response.status_code == 403


def test_valid_refresh_token_returns_a_new_access_token(client: TestClient) -> None:
    tokens = create_login(client)

    response = client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )

    assert response.status_code == 200
    assert response.json()["access_token"]


def test_unknown_refresh_token_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/auth/refresh",
        json={"refresh_token": "missing-token"},
    )

    assert response.status_code == 401


def test_expired_refresh_token_is_rejected(client: TestClient) -> None:
    tokens = create_login(client)
    db = SessionLocal()
    db.query(RefreshToken).filter(
        RefreshToken.token == tokens["refresh_token"]
    ).update(
        {
            RefreshToken.expires_at: (
                datetime.now(timezone.utc) - timedelta(seconds=1)
            ).isoformat()
        }
    )
    db.commit()
    db.close()

    response = client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )

    assert response.status_code == 401


def test_logout_requires_authentication(client: TestClient) -> None:
    response = client.post("/auth/logout")

    assert response.status_code == 401


def test_logout_revokes_the_requesting_users_refresh_tokens(client: TestClient) -> None:
    tokens = create_login(client)

    response = client.post("/auth/logout", headers=auth_header(tokens))
    refresh = client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )

    assert response.status_code == 200
    assert refresh.status_code == 401


def test_unknown_claude_named_model_cannot_bypass_routing_policy(client: TestClient) -> None:
    tokens = create_login(client)

    response = client.post(
        "/chat/",
        headers=auth_header(tokens),
        json={"prompt": "confidential draft", "model_preference": "claude-opus"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_model"


def test_chat_is_exposed_at_the_specified_public_url_without_redirect(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tokens = create_login(client)
    generate = AsyncMock(
        return_value={
            "response": "local response",
            "tokens_used": {"input": 1, "output": 2},
            "duration_ms": 3,
        }
    )
    monkeypatch.setattr(routes_chat.ollama_provider, "generate", generate)

    response = client.post(
        "/chat",
        headers=auth_header(tokens),
        json={"prompt": "Summarize public AI news"},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert response.json()["response"] == "local response"


def test_approved_yellow_request_executes_the_cached_cloud_call(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tokens = create_login(client)
    generate = AsyncMock(
        return_value={
            "response": "approved cloud response",
            "tokens_used": {"input": 3, "output": 4},
            "duration_ms": 7,
        }
    )
    monkeypatch.setattr(routes_chat.claude_provider, "generate", generate)

    pending = client.post(
        "/chat/",
        headers=auth_header(tokens),
        json={"prompt": "confidential draft", "model_preference": "claude-code"},
    )
    approved = client.post(
        "/chat/approve",
        headers=auth_header(tokens),
        json={"request_id": pending.json()["id"], "approved": True},
    )

    assert pending.status_code == 202
    assert approved.status_code == 200
    assert approved.json()["response"] == "approved cloud response"
    assert approved.json()["approval_status"] == "user_approved"
    generate.assert_awaited_once()


def test_green_chat_crosses_the_ollama_http_boundary_and_is_audited(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tokens = create_login(client)
    provider_response = MagicMock()
    provider_response.raise_for_status.return_value = None
    provider_response.json.return_value = {
        "response": "local response",
        "prompt_eval_count": 3,
        "eval_count": 4,
    }
    post = AsyncMock(return_value=provider_response)
    monkeypatch.setattr(routes_chat.ollama_provider.client, "post", post)

    response = client.post(
        "/chat/",
        headers=auth_header(tokens),
        json={"prompt": "Summarize public AI news"},
    )

    assert response.status_code == 200
    assert response.json()["response"] == "local response"
    assert post.await_args.args[0] == "/api/generate"
    db = SessionLocal()
    event = (
        db.query(AuditLog)
        .filter(AuditLog.request_id == response.json()["id"])
        .one()
    )
    db.close()
    assert event.action == "chat_success"
    assert event.result == "success"


def test_approved_red_request_is_forced_to_a_local_model(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tokens = create_login(client)
    local_generate = AsyncMock(
        return_value={
            "response": "local-only response",
            "tokens_used": {"input": 3, "output": 4},
            "duration_ms": 7,
        }
    )
    cloud_generate = AsyncMock()
    monkeypatch.setattr(routes_chat.ollama_provider, "generate", local_generate)
    monkeypatch.setattr(routes_chat.claude_provider, "generate", cloud_generate)

    pending = client.post(
        "/chat/",
        headers=auth_header(tokens),
        json={"prompt": "Meu CPF é 123.456.789-10", "model_preference": "claude-code"},
    )
    approved = client.post(
        "/chat/approve",
        headers=auth_header(tokens),
        json={"request_id": pending.json()["id"], "approved": True},
    )

    assert pending.status_code == 403
    assert approved.status_code == 200
    assert approved.json()["model_used"] == "qwen3.5:2b"
    local_generate.assert_awaited_once()
    cloud_generate.assert_not_awaited()


def test_approval_cache_enforces_owner_and_five_minute_expiry(
    client: TestClient,
) -> None:
    owner_tokens = create_login(client)
    db = SessionLocal()
    other = User(
        username="other",
        password_hash=password_manager.hash_password("SecurePass1!"),
        created_at=datetime.now(timezone.utc).isoformat(),
        is_active=True,
    )
    db.add(other)
    db.commit()
    db.close()
    other_tokens = client.post(
        "/auth/login",
        json={"username": "other", "password": "SecurePass1!"},
    ).json()

    pending = client.post(
        "/chat/",
        headers=auth_header(owner_tokens),
        json={"prompt": "confidential draft", "model_preference": "claude-code"},
    )
    request_id = pending.json()["id"]
    wrong_owner = client.post(
        "/chat/approve",
        headers=auth_header(other_tokens),
        json={"request_id": request_id, "approved": True},
    )
    routes_chat._approval_cache[request_id].expires_at = (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    )
    expired = client.post(
        "/chat/approve",
        headers=auth_header(owner_tokens),
        json={"request_id": request_id, "approved": True},
    )

    assert wrong_owner.status_code == 404
    assert expired.status_code == 410


def test_pending_prompt_is_purged_and_expiry_is_audited_without_approval_access(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routes_chat, "APPROVAL_TTL", timedelta(milliseconds=20))
    tokens = create_login(client)
    pending = client.post(
        "/chat/",
        headers=auth_header(tokens),
        json={"prompt": "confidential draft", "model_preference": "claude-code"},
    )
    request_id = pending.json()["id"]

    time.sleep(0.05)
    expired = client.post(
        "/chat/approve",
        headers=auth_header(tokens),
        json={"request_id": request_id, "approved": True},
    )

    assert request_id not in routes_chat._approval_cache
    assert expired.status_code == 410
    db = SessionLocal()
    expiry_event = (
        db.query(AuditLog)
        .filter(
            AuditLog.request_id == request_id,
            AuditLog.approval_status == "expired",
        )
        .one()
    )
    db.close()
    assert expiry_event.result == "expired"
