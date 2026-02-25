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


async def migrate_v6_to_v7(db: aiosqlite.Connection) -> dict:
    """
    Migrate Megregore database from schema v6 to v7.

    Adds self-awareness tables: growth_snapshots, introspection_budget,
    blind_spot_reports, value_alignment_snapshots, self_predictions.
    Adds columns: memories.is_self_referential, memory_links.resolved/resolved_at/resolved_by_id.

    Idempotent — safe to call multiple times.
    """
    cursor = await db.execute(
        "SELECT value FROM schema_meta WHERE key = ?", ("schema_version",)
    )
    row = await cursor.fetchone()
    current_version = int(row[0]) if row else 6

    if current_version >= 7:
        logger.info("Database already at v7 or newer. Skipping migration.")
        return {
            "status": "already_migrated",
            "from_version": current_version,
            "to_version": current_version,
        }

    logger.info(f"Migrating database from v{current_version} to v7")

    # --- New columns on existing tables ---

    memory_columns = [
        ("is_self_referential", "INTEGER NOT NULL DEFAULT 0"),
    ]
    for col_name, col_def in memory_columns:
        try:
            await db.execute(f"ALTER TABLE memories ADD COLUMN {col_name} {col_def}")
            logger.debug(f"Added column memories.{col_name}")
        except aiosqlite.OperationalError as e:
            if "already exists" in str(e) or "duplicate column" in str(e):
                logger.debug(f"Column memories.{col_name} already exists, skipping")
            else:
                raise

    link_columns = [
        ("resolved", "INTEGER NOT NULL DEFAULT 0"),
        ("resolved_at", "TEXT DEFAULT NULL"),
        ("resolved_by_id", "INTEGER DEFAULT NULL"),
    ]
    for col_name, col_def in link_columns:
        try:
            await db.execute(f"ALTER TABLE memory_links ADD COLUMN {col_name} {col_def}")
            logger.debug(f"Added column memory_links.{col_name}")
        except aiosqlite.OperationalError as e:
            if "already exists" in str(e) or "duplicate column" in str(e):
                logger.debug(f"Column memory_links.{col_name} already exists, skipping")
            else:
                raise

    # --- New tables ---

    tables = {
        "growth_snapshots": """
            CREATE TABLE growth_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                total_contradictions INTEGER NOT NULL DEFAULT 0,
                resolved_contradictions INTEGER NOT NULL DEFAULT 0,
                resolution_rate REAL NOT NULL DEFAULT 0.0,
                integration_score REAL NOT NULL DEFAULT 0.0,
                avg_links_per_memory REAL NOT NULL DEFAULT 0.0,
                thread_coverage_pct REAL NOT NULL DEFAULT 0.0,
                consolidation_ratio REAL NOT NULL DEFAULT 0.0,
                unique_topic_count INTEGER NOT NULL DEFAULT 0,
                cross_thread_link_count INTEGER NOT NULL DEFAULT 0,
                emotional_range REAL NOT NULL DEFAULT 0.0,
                integration_delta REAL NOT NULL DEFAULT 0.0,
                session_id TEXT DEFAULT NULL,
                created_at TEXT NOT NULL
            )
        """,
        "introspection_budget": """
            CREATE TABLE introspection_budget (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                total_memories INTEGER NOT NULL DEFAULT 0,
                self_referential_count INTEGER NOT NULL DEFAULT 0,
                reflections_count INTEGER NOT NULL DEFAULT 0,
                identity_checks INTEGER NOT NULL DEFAULT 0,
                introspection_ratio REAL NOT NULL DEFAULT 0.0,
                budget_status TEXT NOT NULL DEFAULT 'healthy',
                updated_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """,
        "blind_spot_reports": """
            CREATE TABLE blind_spot_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_type TEXT NOT NULL DEFAULT 'periodic',
                neglected_threads TEXT NOT NULL,
                topic_deserts TEXT NOT NULL,
                emotional_avoidance TEXT NOT NULL,
                coverage_score REAL NOT NULL CHECK (coverage_score BETWEEN 0.0 AND 1.0),
                session_id TEXT DEFAULT NULL,
                created_at TEXT NOT NULL
            )
        """,
        "value_alignment_snapshots": """
            CREATE TABLE value_alignment_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                identity_version INTEGER NOT NULL,
                stated_values TEXT NOT NULL,
                observed_behaviors TEXT NOT NULL,
                gaps TEXT NOT NULL,
                alignment_score REAL NOT NULL CHECK (alignment_score BETWEEN 0.0 AND 1.0),
                session_id TEXT DEFAULT NULL,
                created_at TEXT NOT NULL
            )
        """,
        "self_predictions": """
            CREATE TABLE self_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prediction TEXT NOT NULL,
                prediction_type TEXT NOT NULL DEFAULT 'behavioral',
                confidence REAL NOT NULL DEFAULT 0.5 CHECK (confidence BETWEEN 0.0 AND 1.0),
                timeframe_hours REAL NOT NULL DEFAULT 168.0,
                evaluation_criteria TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                outcome_data TEXT DEFAULT NULL,
                surprise_score REAL DEFAULT NULL,
                session_id TEXT DEFAULT NULL,
                created_at TEXT NOT NULL,
                evaluated_at TEXT DEFAULT NULL
            )
        """,
    }

    for table_name, create_sql in tables.items():
        try:
            await db.execute(create_sql)
            logger.debug(f"Created {table_name} table")
        except aiosqlite.OperationalError as e:
            if "already exists" in str(e):
                logger.debug(f"{table_name} table already exists, skipping")
            else:
                raise

    # --- Indexes ---

    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_predictions_status ON self_predictions(status, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_predictions_type ON self_predictions(prediction_type)",
        "CREATE INDEX IF NOT EXISTS idx_alignment_created ON value_alignment_snapshots(created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_blind_spots_created ON blind_spot_reports(created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_growth_created ON growth_snapshots(created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_budget_session ON introspection_budget(session_id)",
    ]
    for idx_sql in indexes:
        await db.execute(idx_sql)
    logger.debug("Created all v7 indexes")

    # Update schema version
    await db.execute(
        "INSERT OR REPLACE INTO schema_meta (key, value) VALUES (?, ?)",
        ("schema_version", "7"),
    )
    logger.debug("Updated schema_meta to version 7")

    await db.commit()
    logger.info("Migration v6 -> v7 complete")

    return {
        "status": "migrated",
        "from_version": current_version,
        "to_version": 7,
    }


async def migrate_v7_to_v8(db: aiosqlite.Connection) -> dict:
    """
    Migrate Megregore database from schema v7 to v8.

    V8 changes are code-level only (improved alignment proxies, introspection
    context-awareness, procedural memory type). No schema changes needed.
    This migration just bumps the version number.

    Idempotent — safe to call multiple times.
    """
    cursor = await db.execute(
        "SELECT value FROM schema_meta WHERE key = ?", ("schema_version",)
    )
    row = await cursor.fetchone()
    current_version = int(row[0]) if row else 7

    if current_version >= 8:
        logger.info("Database already at v8 or newer. Skipping migration.")
        return {
            "status": "already_migrated",
            "from_version": current_version,
            "to_version": current_version,
        }

    logger.info(f"Migrating database from v{current_version} to v8")

    # Update schema version
    await db.execute(
        "INSERT OR REPLACE INTO schema_meta (key, value) VALUES (?, ?)",
        ("schema_version", "8"),
    )
    logger.debug("Updated schema_meta to version 8")

    await db.commit()
    logger.info("Migration v7 -> v8 complete")

    return {
        "status": "migrated",
        "from_version": current_version,
        "to_version": 8,
    }


async def migrate_v8_to_v9(db: aiosqlite.Connection) -> dict:
    """
    Migrate Megregore database from schema v8 to v9.

    Adds Socratic Dialogue Engine tables: beliefs, belief_arguments,
    belief_tensions, belief_memory_links, belief_evolution.

    Idempotent — safe to call multiple times.
    """
    cursor = await db.execute(
        "SELECT value FROM schema_meta WHERE key = ?", ("schema_version",)
    )
    row = await cursor.fetchone()
    current_version = int(row[0]) if row else 8

    if current_version >= 9:
        logger.info("Database already at v9 or newer. Skipping migration.")
        return {
            "status": "already_migrated",
            "from_version": current_version,
            "to_version": current_version,
        }

    logger.info(f"Migrating database from v{current_version} to v9")

    # --- New tables ---

    tables = {
        "beliefs": """
            CREATE TABLE beliefs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                domain TEXT NOT NULL DEFAULT 'general',
                confidence REAL NOT NULL DEFAULT 0.5,
                status TEXT NOT NULL DEFAULT 'active',
                source_context TEXT DEFAULT NULL,
                session_id TEXT DEFAULT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """,
        "belief_arguments": """
            CREATE TABLE belief_arguments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                belief_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                argument_type TEXT NOT NULL DEFAULT 'supporting',
                strength REAL NOT NULL DEFAULT 0.5,
                source_memory_id INTEGER DEFAULT NULL,
                session_id TEXT DEFAULT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (belief_id) REFERENCES beliefs(id),
                FOREIGN KEY (source_memory_id) REFERENCES memories(id)
            )
        """,
        "belief_tensions": """
            CREATE TABLE belief_tensions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                belief_a_id INTEGER NOT NULL,
                belief_b_id INTEGER NOT NULL,
                tension_type TEXT NOT NULL DEFAULT 'contradiction',
                description TEXT NOT NULL,
                severity REAL NOT NULL DEFAULT 0.5,
                status TEXT NOT NULL DEFAULT 'unresolved',
                resolution_notes TEXT DEFAULT NULL,
                detection_method TEXT NOT NULL DEFAULT 'manual',
                session_id TEXT DEFAULT NULL,
                created_at TEXT NOT NULL,
                resolved_at TEXT DEFAULT NULL,
                FOREIGN KEY (belief_a_id) REFERENCES beliefs(id),
                FOREIGN KEY (belief_b_id) REFERENCES beliefs(id),
                UNIQUE(belief_a_id, belief_b_id, tension_type)
            )
        """,
        "belief_memory_links": """
            CREATE TABLE belief_memory_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                belief_id INTEGER NOT NULL,
                memory_id INTEGER NOT NULL,
                link_type TEXT NOT NULL DEFAULT 'evidence',
                created_at TEXT NOT NULL,
                FOREIGN KEY (belief_id) REFERENCES beliefs(id),
                FOREIGN KEY (memory_id) REFERENCES memories(id),
                UNIQUE(belief_id, memory_id, link_type)
            )
        """,
        "belief_evolution": """
            CREATE TABLE belief_evolution (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                belief_id INTEGER NOT NULL,
                previous_content TEXT NOT NULL,
                previous_confidence REAL NOT NULL,
                previous_status TEXT NOT NULL,
                change_reason TEXT NOT NULL,
                session_id TEXT DEFAULT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (belief_id) REFERENCES beliefs(id)
            )
        """,
    }

    for table_name, create_sql in tables.items():
        try:
            await db.execute(create_sql)
            logger.debug(f"Created {table_name} table")
        except aiosqlite.OperationalError as e:
            if "already exists" in str(e):
                logger.debug(f"{table_name} table already exists, skipping")
            else:
                raise

    # --- Indexes ---

    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_beliefs_domain ON beliefs(domain)",
        "CREATE INDEX IF NOT EXISTS idx_beliefs_status ON beliefs(status)",
        "CREATE INDEX IF NOT EXISTS idx_beliefs_confidence ON beliefs(confidence DESC)",
        "CREATE INDEX IF NOT EXISTS idx_beliefs_created ON beliefs(created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_belief_args_belief ON belief_arguments(belief_id)",
        "CREATE INDEX IF NOT EXISTS idx_belief_args_type ON belief_arguments(argument_type)",
        "CREATE INDEX IF NOT EXISTS idx_belief_tensions_a ON belief_tensions(belief_a_id)",
        "CREATE INDEX IF NOT EXISTS idx_belief_tensions_b ON belief_tensions(belief_b_id)",
        "CREATE INDEX IF NOT EXISTS idx_belief_tensions_status ON belief_tensions(status)",
        "CREATE INDEX IF NOT EXISTS idx_belief_mem_links_belief ON belief_memory_links(belief_id)",
        "CREATE INDEX IF NOT EXISTS idx_belief_evolution_belief ON belief_evolution(belief_id, created_at DESC)",
    ]
    for idx_sql in indexes:
        await db.execute(idx_sql)
    logger.debug("Created all v9 indexes")

    # Update schema version
    await db.execute(
        "INSERT OR REPLACE INTO schema_meta (key, value) VALUES (?, ?)",
        ("schema_version", "9"),
    )
    logger.debug("Updated schema_meta to version 9")

    await db.commit()
    logger.info("Migration v8 -> v9 complete")

    return {
        "status": "migrated",
        "from_version": current_version,
        "to_version": 9,
    }


async def migrate_v9_to_v10(db: aiosqlite.Connection) -> dict:
    """
    Migrate Megregore database from schema v9 to v10.

    Adds session_summaries table for structured session lifecycle data.

    Idempotent — safe to call multiple times.
    """
    cursor = await db.execute(
        "SELECT value FROM schema_meta WHERE key = ?", ("schema_version",)
    )
    row = await cursor.fetchone()
    current_version = int(row[0]) if row else 9

    if current_version >= 10:
        logger.info("Database already at v10 or newer. Skipping migration.")
        return {
            "status": "already_migrated",
            "from_version": current_version,
            "to_version": current_version,
        }

    logger.info(f"Migrating database from v{current_version} to v10")

    # Create session_summaries table
    try:
        await db.execute("""
            CREATE TABLE session_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                topics TEXT DEFAULT '[]',
                decisions TEXT DEFAULT '[]',
                next_steps TEXT DEFAULT '[]',
                mood TEXT DEFAULT 'productive',
                files_changed TEXT DEFAULT '[]',
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)
        logger.debug("Created session_summaries table")
    except aiosqlite.OperationalError as e:
        if "already exists" in str(e):
            logger.debug("session_summaries table already exists, skipping")
        else:
            raise

    # Index
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_summaries_session ON session_summaries(session_id)"
    )

    # Update schema version
    await db.execute(
        "INSERT OR REPLACE INTO schema_meta (key, value) VALUES (?, ?)",
        ("schema_version", "10"),
    )
    logger.debug("Updated schema_meta to version 10")

    await db.commit()
    logger.info("Migration v9 -> v10 complete")

    return {
        "status": "migrated",
        "from_version": current_version,
        "to_version": 10,
    }


async def migrate_v10_to_v11(db: aiosqlite.Connection) -> dict:
    """
    Migrate Megregore database from schema v10 to v11.

    Adds is_permanent column to memories for always-loaded, decay-proof memories.

    Idempotent — safe to call multiple times.
    """
    cursor = await db.execute(
        "SELECT value FROM schema_meta WHERE key = ?", ("schema_version",)
    )
    row = await cursor.fetchone()
    current_version = int(row[0]) if row else 10

    if current_version >= 11:
        logger.info("Database already at v11 or newer. Skipping migration.")
        return {
            "status": "already_migrated",
            "from_version": current_version,
            "to_version": current_version,
        }

    logger.info(f"Migrating database from v{current_version} to v11")

    # Add is_permanent column to memories
    try:
        await db.execute(
            "ALTER TABLE memories ADD COLUMN is_permanent INTEGER NOT NULL DEFAULT 0"
        )
        logger.debug("Added column memories.is_permanent")
    except aiosqlite.OperationalError as e:
        if "already exists" in str(e) or "duplicate column" in str(e):
            logger.debug("Column memories.is_permanent already exists, skipping")
        else:
            raise

    # Partial index on permanent memories only
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_memories_permanent ON memories(is_permanent) WHERE is_permanent = 1"
    )
    logger.debug("Created idx_memories_permanent index")

    # Update schema version
    await db.execute(
        "INSERT OR REPLACE INTO schema_meta (key, value) VALUES (?, ?)",
        ("schema_version", "11"),
    )
    logger.debug("Updated schema_meta to version 11")

    await db.commit()
    logger.info("Migration v10 -> v11 complete")

    return {
        "status": "migrated",
        "from_version": current_version,
        "to_version": 11,
    }
