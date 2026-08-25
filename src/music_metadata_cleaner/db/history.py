"""Operation history repository."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid

from music_metadata_cleaner.app.metadata_codec import metadata_from_dict, metadata_to_dict
from music_metadata_cleaner.domain.models import MetadataUpdate, TrackMetadata


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class OperationRecord:
    operation_id: str
    batch_id: str
    file_path: Path
    original_filename: str
    new_filename: str | None
    original_metadata: TrackMetadata
    new_metadata: TrackMetadata
    status: str
    created_at: str
    updated_at: str
    error_message: str | None = None


@dataclass(frozen=True)
class BatchRecord:
    batch_id: str
    created_at: str
    status: str


class HistoryRepository:
    """SQLite-backed file operation history."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def begin_batch(self) -> str:
        batch_id = uuid.uuid4().hex
        now = utc_now_iso()
        with self.connection:
            self.connection.execute(
                "INSERT INTO operation_batches(batch_id, created_at, status) VALUES (?, ?, ?)",
                (batch_id, now, "pending"),
            )
        return batch_id

    def create_operation(
        self,
        *,
        batch_id: str,
        file_path: Path,
        original_metadata: TrackMetadata,
        new_metadata: MetadataUpdate,
        new_filename: str | None,
    ) -> str:
        operation_id = uuid.uuid4().hex
        now = utc_now_iso()
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO file_operations(
                    operation_id, batch_id, file_path, original_filename, new_filename,
                    original_metadata_json, new_metadata_json, status, created_at, updated_at, error_message
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    operation_id,
                    batch_id,
                    str(file_path),
                    file_path.name,
                    new_filename,
                    json.dumps(metadata_to_dict(original_metadata), ensure_ascii=False),
                    json.dumps(metadata_to_dict(new_metadata), ensure_ascii=False),
                    "pending",
                    now,
                    now,
                    None,
                ),
            )
        return operation_id

    def mark_operation(self, operation_id: str, status: str, error_message: str | None = None) -> None:
        with self.connection:
            self.connection.execute(
                "UPDATE file_operations SET status = ?, updated_at = ?, error_message = ? WHERE operation_id = ?",
                (status, utc_now_iso(), error_message, operation_id),
            )

    def mark_batch(self, batch_id: str, status: str) -> None:
        with self.connection:
            self.connection.execute("UPDATE operation_batches SET status = ? WHERE batch_id = ?", (status, batch_id))

    def list_operations(self, limit: int = 100) -> list[OperationRecord]:
        rows = self.connection.execute(
            """
            SELECT * FROM file_operations
            ORDER BY datetime(created_at) DESC, operation_id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [self._row_to_operation(row) for row in rows]

    def list_batches(self, limit: int = 50) -> list[BatchRecord]:
        rows = self.connection.execute(
            """
            SELECT * FROM operation_batches
            ORDER BY datetime(created_at) DESC, batch_id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [BatchRecord(batch_id=row["batch_id"], created_at=row["created_at"], status=row["status"]) for row in rows]

    def latest_applied_batch_id(self) -> str | None:
        row = self.connection.execute(
            """
            SELECT batch_id FROM operation_batches
            WHERE status = 'applied'
            ORDER BY datetime(created_at) DESC, batch_id DESC
            LIMIT 1
            """
        ).fetchone()
        return str(row["batch_id"]) if row else None

    def operations_for_batch(self, batch_id: str) -> list[OperationRecord]:
        rows = self.connection.execute(
            """
            SELECT * FROM file_operations
            WHERE batch_id = ?
            ORDER BY datetime(created_at) DESC, operation_id DESC
            """,
            (batch_id,),
        ).fetchall()
        return [self._row_to_operation(row) for row in rows]

    def _row_to_operation(self, row: sqlite3.Row) -> OperationRecord:
        return OperationRecord(
            operation_id=row["operation_id"],
            batch_id=row["batch_id"],
            file_path=Path(row["file_path"]),
            original_filename=row["original_filename"],
            new_filename=row["new_filename"],
            original_metadata=metadata_from_dict(json.loads(row["original_metadata_json"])),
            new_metadata=metadata_from_dict(json.loads(row["new_metadata_json"])),
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            error_message=row["error_message"],
        )

