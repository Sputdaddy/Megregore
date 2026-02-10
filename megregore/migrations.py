"""Idempotent schema migrations for Megregore. Handles upgrading the database schema."""

import logging
from datetime import datetime, timezone

import aiosqlite

logger = logging.getLogger("megregore.migrations")


def _now() -> str:
    """Current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


async def migrate_v4_to_v5(db: aiosqlite.Connection) -> dict:
    """
    Migrate Megregore database from schema v4 to v5.

    Adds activation tracking, threading support, and access logging.

    Args:
        db: aiosqlite connection with foreign keys enabled.

    Returns:
        dict with keys:
            - status: "already_migrated" or "migrated"
            - from_version: integer version before migration
            - to_version: integer version after migration

    Idempotent — safe to call multiple times. Handles existing columns gracefully.
    """
    # Check current schema version
    cursor = await db.execute(
        "SELECT value FROM schema_meta WHERE key = ?", ("schema_version",)
    )
    row = await cursor.fetchone()
    current_version = int(row[0]) if row else 4

    if current_version >= 5:
        logger.info("Database already at v5 or newer. Skipping migration.")
        return {
            "status": "already_migrated",
            "from_version": current_version,
            "to_version": current_version,
        }

    logger.info(f"Migrating database from v{current_version} to v5")

    # Add new columns to memories table with graceful error handling
    memory_columns = [
        ("activation_level", "REAL DEFAULT 1.0"),
        ("last_activation_decay", "TEXT DEFAULT NULL"),
        ("thread_id", "INTEGER DEFAULT NULL"),
    ]

    for col_name, col_def in memory_columns:
        try:
            await db.execute(f"ALTER TABLE memories ADD COLUMN {col_name} {col_def}")
            logger.debug(f"Added column memories.{col_name}")
        except aiosqlite.OperationalError as e:
            if "already exists" in str(e):
                logger.debug(f"Column memories.{col_name} already exists, skipping")
            else:
                raise

    # Create threads table
    try:
        await db.execute(
            """
            CREATE TABLE threads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT DEFAULT NULL,
                created_at TEXT NOT NULL,
                last_active TEXT NOT NULL,
                memory_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        logger.debug("Created threads table")
    except aiosqlite.OperationalError as e:
        if "already exists" in str(e):
            logger.debug("threads table already exists, skipping")
        else:
            raise

    # Create memory_access_log table
    try:
        await db.execute(
            """
            CREATE TABLE memory_access_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_id INTEGER NOT NULL,
                access_type TEXT NOT NULL,
                context_json TEXT DEFAULT NULL,
                session_id TEXT DEFAULT NULL,
                accessed_at TEXT NOT NULL,
                FOREIGN KEY (memory_id) REFERENCES memories(id)
            )
            """
        )
        logger.debug("Created memory_access_log table")
    except aiosqlite.OperationalError as e:
        if "already exists" in str(e):
            logger.debug("memory_access_log table already exists, skipping")
        else:
            raise

    # Create performance indexes
    indexes = [
        (
            "idx_memories_activation",
            "CREATE INDEX IF NOT EXISTS idx_memories_activation ON memories(activation_level DESC)",
        ),
        (
            "idx_memories_thread",
            "CREATE INDEX IF NOT EXISTS idx_memories_thread ON memories(thread_id)",
        ),
        (
            "idx_access_log_memory",
            "CREATE INDEX IF NOT EXISTS idx_access_log_memory ON memory_access_log(memory_id, accessed_at DESC)",
        ),
        (
            "idx_access_log_session",
            "CREATE INDEX IF NOT EXISTS idx_access_log_session ON memory_access_log(session_id, accessed_at DESC)",
        ),
    ]

    for idx_name, idx_sql in indexes:
        try:
            await db.execute(idx_sql)
            logger.debug(f"Created index {idx_name}")
        except aiosqlite.OperationalError as e:
            if "already exists" in str(e):
                logger.debug(f"Index {idx_name} already exists, skipping")
            else:
                raise

    # Update schema version
    await db.execute(
        "INSERT OR REPLACE INTO schema_meta (key, value) VALUES (?, ?)",
        ("schema_version", "5"),
    )
    logger.debug("Updated schema_meta to version 5")

    # Commit all changes
    await db.commit()
    logger.info("Migration v4 -> v5 complete")

    return {
        "status": "migrated",
        "from_version": current_version,
        "to_version": 5,
    }


async def migrate_v5_to_v6(db: aiosqlite.Connection) -> dict:
    """
    Migrate Megregore database from schema v5 to v6.

    Adds source column to memory_links to distinguish manual vs auto-inferred links.

    Args:
        db: aiosqlite connection with foreign keys enabled.

    Returns:
        dict with status, from_version, to_version.

    Idempotent — safe to call multiple times.
    """
    cursor = await db.execute(
        "SELECT value FROM schema_meta WHERE key = ?", ("schema_version",)
    )
    row = await cursor.fetchone()
    current_version = int(row[0]) if row else 5

    if current_version >= 6:
        logger.info("Database already at v6 or newer. Skipping migration.")
        return {
            "status": "already_migrated",
            "from_version": current_version,
            "to_version": current_version,
        }

    logger.info(f"Migrating database from v{current_version} to v6")

    # Add source column to memory_links
    try:
        await db.execute(
            "ALTER TABLE memory_links ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'"
        )
        logger.debug("Added column memory_links.source")
    except aiosqlite.OperationalError as e:
        if "already exists" in str(e):
            logger.debug("Column memory_links.source already exists, skipping")
        else:
            raise

    # Update schema version
    await db.execute(
        "INSERT OR REPLACE INTO schema_meta (key, value) VALUES (?, ?)",
        ("schema_version", "6"),
    )
    logger.debug("Updated schema_meta to version 6")

    await db.commit()
    logger.info("Migration v5 -> v6 complete")

    return {
        "status": "migrated",
        "from_version": current_version,
        "to_version": 6,
    }
