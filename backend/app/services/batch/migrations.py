"""SQLite schema for the batch-upload feature.

One file, one ``apply()`` function, idempotent. Future migrations append
to ``MIGRATIONS`` and the runner replays only the ones not yet recorded
in ``schema_migrations``.

Why hand-rolled rather than Alembic: the schema is three tables, the
prototype's only consumer is in-process, and a migration framework would
add operational surface (CLI, env wiring) we cannot justify here. The
deferred upgrade to Postgres can adopt Alembic at that point in one go.
"""

from __future__ import annotations

import sqlite3

# Each migration is (version_int, sql_str). Versions are dense, monotonic.
# Never edit a previously-applied migration; append a new one instead.
MIGRATIONS: tuple[tuple[int, str], ...] = (
    (
        1,
        # Note: schema_migrations is created by apply() before any migration
        # runs, so it must NOT be re-declared here. Earlier drafts duplicated
        # it; keep this migration focused on the feature tables.
        """
        CREATE TABLE IF NOT EXISTS batches (
            id TEXT PRIMARY KEY,
            importer_name TEXT NOT NULL,
            importer_email TEXT NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS applications (
            id TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
            -- Importer-supplied COLA fields (TTB Step 2 of 3).
            serial_number TEXT NOT NULL,
            brand_name TEXT,
            fanciful_name TEXT,
            class_type TEXT,
            alcohol_content TEXT,
            net_contents TEXT,
            bottler TEXT,
            country_of_origin TEXT,
            -- Pipeline state.
            processing_status TEXT NOT NULL DEFAULT 'pending',
            workflow_status TEXT NOT NULL DEFAULT 'pending_review',
            -- Analysis output (JSON-encoded AnalyzeResponse). NULL until done.
            analyze_response_json TEXT,
            error_code TEXT,
            error_message TEXT,
            -- Timestamps + audit.
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            processed_at TEXT,
            decided_at TEXT,
            decided_note TEXT,
            UNIQUE (batch_id, serial_number)
        );

        CREATE INDEX IF NOT EXISTS idx_applications_batch
            ON applications (batch_id);
        CREATE INDEX IF NOT EXISTS idx_applications_workflow
            ON applications (workflow_status);
        CREATE INDEX IF NOT EXISTS idx_applications_processing
            ON applications (processing_status);

        CREATE TABLE IF NOT EXISTS label_images (
            id TEXT PRIMARY KEY,
            application_id TEXT NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
            filename TEXT NOT NULL,
            stored_path TEXT NOT NULL,
            attribution TEXT NOT NULL DEFAULT 'other',
            is_primary INTEGER NOT NULL DEFAULT 0,
            byte_size INTEGER NOT NULL,
            content_type TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_label_images_app
            ON label_images (application_id);
        """,
    ),
)


def apply(conn: sqlite3.Connection) -> None:
    """Apply all pending migrations on the given connection.

    Idempotent: safe to call on every startup. Wraps each migration in
    its own transaction so a partial failure does not leave the schema
    half-migrated.
    """
    # Bootstrap the migrations table itself before we can SELECT from it.
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )
    conn.commit()

    cur = conn.execute("SELECT version FROM schema_migrations")
    applied = {row[0] for row in cur.fetchall()}

    for version, sql in MIGRATIONS:
        if version in applied:
            continue
        with conn:  # transaction
            conn.executescript(sql)
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations (version) VALUES (?)",
                (version,),
            )
