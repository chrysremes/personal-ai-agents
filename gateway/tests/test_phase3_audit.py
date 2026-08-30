"""Audit event, query, redaction, and retention acceptance tests."""

from datetime import datetime, timedelta, timezone
import gzip
import json
import logging
from pathlib import Path

import pytest

from audit import db_audit_logger
from classifier import redact_red_data
from db import SessionLocal, reset_db
from logging_config import RedactedJSONFormatter, audit_logger
from models import AuditLog


@pytest.fixture(autouse=True)
def isolated_database() -> None:
    reset_db()


@pytest.mark.asyncio
async def test_multiple_events_can_share_one_request_correlation_id() -> None:
    await db_audit_logger.log_action(request_id="request-1", action="pending", result="success")
    await db_audit_logger.log_action(request_id="request-1", action="approved", result="success")

    db = SessionLocal()
    entries = db.query(AuditLog).order_by(AuditLog.id).all()
    db.close()

    assert [entry.request_id for entry in entries] == ["request-1", "request-1"]
    assert entries[0].event_id != entries[1].event_id


@pytest.mark.asyncio
async def test_audit_logger_waits_until_database_event_is_persisted() -> None:
    await audit_logger.log_action(request_id="request-2", action="chat", result="success")

    db = SessionLocal()
    assert db.query(AuditLog).filter(AuditLog.request_id == "request-2").count() == 1
    db.close()


@pytest.mark.asyncio
async def test_stdout_and_database_receive_redacted_errors(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="gateway.audit")
    sensitive = "CPF 123.456.789-10 failed for conta corrente"

    await audit_logger.log_action(
        request_id="request-3",
        action="chat_error",
        result="error",
        error=sensitive,
    )

    db = SessionLocal()
    entry = db.query(AuditLog).filter(AuditLog.request_id == "request-3").one()
    db.close()
    stdout_event = next(
        record.getMessage() for record in caplog.records if "request-3" in record.getMessage()
    )
    assert "123.456.789-10" not in stdout_event
    assert "conta corrente" not in stdout_event.lower()
    assert "123.456.789-10" not in entry.error_message
    assert "conta corrente" not in entry.error_message.lower()


@pytest.mark.asyncio
async def test_query_total_counts_all_matching_rows_before_limit() -> None:
    for index in range(3):
        await db_audit_logger.log_action(
            user_id=7,
            request_id=f"request-{index}",
            action="chat",
            result="success",
        )

    logs, total = await db_audit_logger.query_logs(user_id=7, limit=1)

    assert len(logs) == 1
    assert total == 3


@pytest.mark.parametrize(
    "error",
    [
        "CPF 123.456.789-10",
        "CPF 12345678910",
        "agência indisponível",
        "conta corrente indisponível",
        "transferência recusada",
        "CNPJ 12.345.678/0001-90",
        "RG: inválido",
        "minha senha é hunter2",
    ],
)
def test_database_redactor_covers_each_red_category(error: str) -> None:
    redacted = db_audit_logger._redact_error(error)

    assert redacted != error
    assert "[REDACTED:" in redacted


def test_redaction_is_stable_when_multiple_log_sinks_apply_it() -> None:
    redacted = redact_red_data("CPF 123.456.789-10")

    assert redact_red_data(redacted) == redacted


def test_structured_application_logs_apply_the_shared_red_rules() -> None:
    formatter = RedactedJSONFormatter()

    redacted = formatter._redact("CPF 123.456.789-10 failed for conta corrente")

    assert "123.456.789-10" not in redacted
    assert "conta corrente" not in redacted.lower()


@pytest.mark.asyncio
async def test_archive_moves_only_expired_events_to_searchable_gzip(tmp_path: Path) -> None:
    from audit_archive import archive_old_audit_logs

    now = datetime(2026, 8, 30, tzinfo=timezone.utc)
    for request_id in ("old-1", "old-2", "new-1"):
        await db_audit_logger.log_action(
            request_id=request_id,
            action="chat",
            result="success",
        )

    db = SessionLocal()
    old_timestamp = (now - timedelta(days=91)).isoformat().replace("+00:00", "Z")
    db.query(AuditLog).filter(AuditLog.request_id.in_(["old-1", "old-2"])).update(
        {AuditLog.timestamp: old_timestamp},
        synchronize_session=False,
    )
    db.commit()
    db.close()

    result = archive_old_audit_logs(
        now=now,
        retention_days=90,
        archive_path=tmp_path,
    )

    assert result.archived_count == 2
    assert result.path is not None and result.path.suffix == ".gz"
    with gzip.open(result.path, "rt", encoding="utf-8") as archive:
        archived = [json.loads(line) for line in archive]
    assert {event["request_id"] for event in archived} == {"old-1", "old-2"}
    db = SessionLocal()
    assert {entry.request_id for entry in db.query(AuditLog).all()} == {"new-1"}
    db.close()
