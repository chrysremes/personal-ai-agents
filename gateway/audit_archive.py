"""Manual retention command for timestamped gzip audit archives."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import gzip
import json
from pathlib import Path
from typing import Optional

from audit import audit_entry_to_dict
from config import settings
from db import SessionLocal
from models import AuditLog


@dataclass(frozen=True)
class ArchiveResult:
    """Outcome of one retention run."""

    archived_count: int
    path: Optional[Path]


def archive_old_audit_logs(
    *,
    now: Optional[datetime] = None,
    retention_days: Optional[int] = None,
    archive_path: Optional[Path] = None,
) -> ArchiveResult:
    """Archive and then delete audit events older than the retention window."""
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    days = retention_days if retention_days is not None else settings.audit_retention_days
    destination = archive_path or Path(settings.audit_archive_path)
    cutoff = (current_time - timedelta(days=days)).isoformat().replace("+00:00", "Z")

    db = SessionLocal()
    try:
        entries = (
            db.query(AuditLog)
            .filter(AuditLog.timestamp < cutoff)
            .order_by(AuditLog.timestamp, AuditLog.id)
            .all()
        )
        if not entries:
            return ArchiveResult(archived_count=0, path=None)

        destination.mkdir(parents=True, exist_ok=True)
        timestamp = current_time.strftime("%Y%m%dT%H%M%S%fZ")
        final_path = destination / f"audit-logs-{timestamp}.jsonl.gz"
        temporary_path = destination / f".{final_path.name}.tmp"

        with gzip.open(temporary_path, "wt", encoding="utf-8") as archive:
            for entry in entries:
                archive.write(
                    json.dumps(audit_entry_to_dict(entry), ensure_ascii=False) + "\n"
                )
        temporary_path.replace(final_path)

        entry_ids = [entry.id for entry in entries]
        db.query(AuditLog).filter(AuditLog.id.in_(entry_ids)).delete(
            synchronize_session=False
        )
        db.commit()
        return ArchiveResult(archived_count=len(entry_ids), path=final_path)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    result = archive_old_audit_logs()
    print(
        f"Archived {result.archived_count} audit events"
        + (f" to {result.path}" if result.path else "")
    )
