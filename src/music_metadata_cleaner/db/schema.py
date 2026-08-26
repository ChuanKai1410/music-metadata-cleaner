"""SQLite schema management."""

from __future__ import annotations

import sqlite3


SCHEMA_VERSION = 1


def initialize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY
        );

        CREATE TABLE IF NOT EXISTS operation_batches (
            batch_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS file_operations (
            operation_id TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL,
            file_path TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            new_filename TEXT,
            original_metadata_json TEXT NOT NULL,
            new_metadata_json TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            error_message TEXT,
            FOREIGN KEY(batch_id) REFERENCES operation_batches(batch_id)
        );

        CREATE INDEX IF NOT EXISTS idx_file_operations_batch
            ON file_operations(batch_id);

        CREATE TABLE IF NOT EXISTS request_cache (
            cache_key TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    connection.execute("INSERT OR IGNORE INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))
    connection.commit()

