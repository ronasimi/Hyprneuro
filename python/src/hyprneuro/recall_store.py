"""Proposed local SQLite Recall schema, intentionally NOT migrated or enabled."""
from dataclasses import dataclass


SCHEMA_SQL = """
-- TODO(migration): Version this against storage.Store before applying.
CREATE TABLE IF NOT EXISTS recall_observations (
    id TEXT PRIMARY KEY,
    observed_at TEXT NOT NULL,
    monotonic_ns INTEGER NOT NULL,
    boot_id TEXT,
    workspace_id TEXT NOT NULL,
    output_name TEXT,
    app_id TEXT,
    window_title TEXT,
    capture_sha256 TEXT NOT NULL,
    ocr_text TEXT NOT NULL,
    description TEXT NOT NULL,
    model_name TEXT NOT NULL,
    created_unix_seconds REAL NOT NULL
);
-- TODO(fts): Separate, retention-aware FTS5 index over OCR and description.
"""


@dataclass(frozen=True)
class RecallObservation:
    id: str
    observed_at: str
    workspace_id: str
    output_name: str | None
    app_id: str | None
    ocr_text: str
    description: str
    capture_sha256: str


class RecallRepository:
    def __init__(self, store):
        self.store = store

    def save(self, observation: RecallObservation):
        # TODO: atomic SQLite insert, optional FTS, bounded text, retention.
        # Never write screenshot PNG or other raw capture bytes to the DB.
        raise NotImplementedError("Recall storage is disabled")

    def search(self, query: str, limit: int = 20):
        # TODO: offline chronological + full-text retrieval, purge and exclusion.
        raise NotImplementedError("Recall search is disabled")
