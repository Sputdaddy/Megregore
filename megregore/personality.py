"""Personality evolution system for Megregore. Tracks traits, preferences, and voice patterns."""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from . import database

logger = logging.getLogger("megregore.personality")

# Validation constants
VALID_TRAIT_CATEGORIES = {"communication", "emotional", "cognitive", "social", "aesthetic", "general"}
VALID_PREFERENCE_DOMAINS = {"coding", "communication", "aesthetic", "philosophical", "social", "general"}
VALID_PREFERENCE_STATUSES = {"active", "evolved", "faded", "contradicted"}
VALID_VOICE_NOTE_TYPES = {"pattern", "phrase", "habit", "observation", "evolution"}
VALID_VOICE_NOTE_STATUSES = {"active", "retired", "evolved"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Trait Functions ---


async def record_trait(name: str, value: float = 0.5, description: str = "",
                       category: str = "general", anchors: Optional[dict] = None,
                       session_id: Optional[str] = None) -> dict:
    """Create a new personality trait. Name must be unique."""
    db = await database.get_connection()
    now = _now()
    anchors_json = json.dumps(anchors or {})
    cursor = await db.execute(
        """INSERT INTO personality_traits (name, category, value, description, anchors, session_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (name, category, value, description, anchors_json, session_id, now, now),
    )
    trait_id = cursor.lastrowid
    await db.commit()

    cursor = await db.execute("SELECT * FROM personality_traits WHERE id = ?", (trait_id,))
    row = await cursor.fetchone()
    result = dict(row)
    result["anchors"] = json.loads(result["anchors"])
    return result


async def update_trait(trait_id: int, value: Optional[float] = None,
                       description: Optional[str] = None, change_reason: str = "",
                       source_memory_id: Optional[int] = None,
                       session_id: Optional[str] = None) -> Optional[dict]:
    """Update a trait, saving current state to history first."""
    db = await database.get_connection()

    cursor = await db.execute(
        "SELECT * FROM personality_traits WHERE id = ?", (trait_id,)
    )
    row = await cursor.fetchone()
    if not row:
        return None
    current = dict(row)

    now = _now()
    new_value = value if value is not None else current["value"]
    new_description = description if description is not None else current["description"]
    change_magnitude = abs(new_value - current["value"])

    # Save to history
    await db.execute(
        """INSERT INTO trait_history
        (trait_id, previous_value, previous_description, new_value, new_description,
         change_reason, change_magnitude, source_memory_id, session_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (trait_id, current["value"], current["description"],
         new_value, new_description, change_reason, change_magnitude,
         source_memory_id, session_id, now),
    )

    # Update trait
    updates = ["updated_at = ?"]
    params = [now]
    if value is not None:
        updates.append("value = ?")
        params.append(value)
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    params.append(trait_id)

    await db.execute(
        f"UPDATE personality_traits SET {', '.join(updates)} WHERE id = ?", params
    )
    await db.commit()

    cursor = await db.execute("SELECT * FROM personality_traits WHERE id = ?", (trait_id,))
    row = await cursor.fetchone()
    result = dict(row)
    result["anchors"] = json.loads(result["anchors"])
    return result


async def get_trait(trait_id: int) -> Optional[dict]:
    """Get a trait by ID with parsed anchors."""
    db = await database.get_connection()
    cursor = await db.execute("SELECT * FROM personality_traits WHERE id = ?", (trait_id,))
    row = await cursor.fetchone()
    if not row:
        return None
    result = dict(row)
    result["anchors"] = json.loads(result["anchors"])
    return result


async def get_trait_by_name(name: str) -> Optional[dict]:
    """Get a trait by name (case-insensitive)."""
    db = await database.get_connection()
    cursor = await db.execute(
        "SELECT * FROM personality_traits WHERE LOWER(name) = LOWER(?)", (name,)
    )
    row = await cursor.fetchone()
    if not row:
        return None
    result = dict(row)
    result["anchors"] = json.loads(result["anchors"])
    return result


async def list_traits(category: Optional[str] = None, limit: int = 50) -> list[dict]:
    """List traits, optionally filtered by category."""
    db = await database.get_connection()

    if category:
        cursor = await db.execute(
            "SELECT * FROM personality_traits WHERE category = ? ORDER BY name LIMIT ?",
            (category, limit),
        )
    else:
        cursor = await db.execute(
            "SELECT * FROM personality_traits ORDER BY name LIMIT ?", (limit,)
        )
    rows = await cursor.fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["anchors"] = json.loads(d["anchors"])
        results.append(d)
    return results


async def get_trait_history(trait_id: int, limit: int = 20) -> list[dict]:
    """Get change history for a trait, most recent first."""
    db = await database.get_connection()
    cursor = await db.execute(
        "SELECT * FROM trait_history WHERE trait_id = ? ORDER BY created_at DESC LIMIT ?",
        (trait_id, limit),
    )
    return [dict(r) for r in await cursor.fetchall()]


async def get_trait_trajectory(trait_id: int, limit: int = 50) -> list[dict]:
    """Get chronological value history for charting. Oldest first."""
    db = await database.get_connection()
    cursor = await db.execute(
        """SELECT created_at, new_value as value, change_reason
        FROM trait_history WHERE trait_id = ? ORDER BY created_at ASC LIMIT ?""",
        (trait_id, limit),
    )
    return [dict(r) for r in await cursor.fetchall()]


# --- Preference Functions ---


async def record_preference(content: str, domain: str = "general", strength: float = 0.5,
                             sentiment: float = 0.0, context: Optional[str] = None,
                             session_id: Optional[str] = None) -> dict:
    """Record a new preference."""
    db = await database.get_connection()
    now = _now()
    cursor = await db.execute(
        """INSERT INTO preferences (content, domain, strength, sentiment, status, context, session_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?)""",
        (content, domain, strength, sentiment, context, session_id, now, now),
    )
    pref_id = cursor.lastrowid
    await db.commit()

    cursor = await db.execute("SELECT * FROM preferences WHERE id = ?", (pref_id,))
    row = await cursor.fetchone()
    return dict(row)


async def update_preference(preference_id: int, content: Optional[str] = None,
                              strength: Optional[float] = None, sentiment: Optional[float] = None,
                              status: Optional[str] = None, change_reason: str = "",
                              session_id: Optional[str] = None) -> Optional[dict]:
    """Update a preference, saving current state to history first."""
    db = await database.get_connection()

    cursor = await db.execute(
        "SELECT * FROM preferences WHERE id = ?", (preference_id,)
    )
    row = await cursor.fetchone()
    if not row:
        return None
    current = dict(row)

    now = _now()

    # Save to history
    await db.execute(
        """INSERT INTO preference_history
        (preference_id, previous_content, previous_strength, previous_sentiment,
         previous_status, change_reason, session_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (preference_id, current["content"], current["strength"], current["sentiment"],
         current["status"], change_reason, session_id, now),
    )

    # Build dynamic update
    updates = ["updated_at = ?"]
    params = [now]
    if content is not None:
        updates.append("content = ?")
        params.append(content)
    if strength is not None:
        updates.append("strength = ?")
        params.append(strength)
    if sentiment is not None:
        updates.append("sentiment = ?")
        params.append(sentiment)
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    params.append(preference_id)

    await db.execute(
        f"UPDATE preferences SET {', '.join(updates)} WHERE id = ?", params
    )
    await db.commit()

    cursor = await db.execute("SELECT * FROM preferences WHERE id = ?", (preference_id,))
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_preference(preference_id: int) -> Optional[dict]:
    """Get a preference with its change history."""
    db = await database.get_connection()

    cursor = await db.execute("SELECT * FROM preferences WHERE id = ?", (preference_id,))
    row = await cursor.fetchone()
    if not row:
        return None
    pref = dict(row)

    cursor = await db.execute(
        "SELECT * FROM preference_history WHERE preference_id = ? ORDER BY created_at DESC",
        (preference_id,),
    )
    pref["history"] = [dict(r) for r in await cursor.fetchall()]
    return pref


async def list_preferences(domain: Optional[str] = None, status: Optional[str] = None,
                             min_strength: Optional[float] = None,
                             limit: int = 50) -> list[dict]:
    """List preferences with optional filters."""
    db = await database.get_connection()

    conditions = []
    params = []
    if domain:
        conditions.append("domain = ?")
        params.append(domain)
    if status:
        conditions.append("status = ?")
        params.append(status)
    if min_strength is not None:
        conditions.append("strength >= ?")
        params.append(min_strength)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    cursor = await db.execute(
        f"SELECT * FROM preferences {where} ORDER BY strength DESC LIMIT ?",
        params + [limit],
    )
    return [dict(r) for r in await cursor.fetchall()]


async def get_preference_history(preference_id: int, limit: int = 20) -> list[dict]:
    """Get change history for a preference."""
    db = await database.get_connection()
    cursor = await db.execute(
        "SELECT * FROM preference_history WHERE preference_id = ? ORDER BY created_at DESC LIMIT ?",
        (preference_id, limit),
    )
    return [dict(r) for r in await cursor.fetchall()]


# --- Voice Note Functions ---


async def record_voice_note(content: str, note_type: str = "observation",
                              source_context: Optional[str] = None,
                              session_id: Optional[str] = None) -> dict:
    """Record a voice/style observation."""
    db = await database.get_connection()
    now = _now()
    cursor = await db.execute(
        """INSERT INTO voice_notes (content, note_type, status, source_context, session_id, created_at, updated_at)
        VALUES (?, ?, 'active', ?, ?, ?, ?)""",
        (content, note_type, source_context, session_id, now, now),
    )
    note_id = cursor.lastrowid
    await db.commit()

    cursor = await db.execute("SELECT * FROM voice_notes WHERE id = ?", (note_id,))
    row = await cursor.fetchone()
    return dict(row)


async def update_voice_note(note_id: int, content: Optional[str] = None,
                              status: Optional[str] = None, note_type: Optional[str] = None,
                              session_id: Optional[str] = None) -> Optional[dict]:
    """Update a voice note."""
    db = await database.get_connection()

    cursor = await db.execute("SELECT * FROM voice_notes WHERE id = ?", (note_id,))
    row = await cursor.fetchone()
    if not row:
        return None

    now = _now()
    updates = ["updated_at = ?"]
    params = [now]
    if content is not None:
        updates.append("content = ?")
        params.append(content)
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if note_type is not None:
        updates.append("note_type = ?")
        params.append(note_type)
    params.append(note_id)

    await db.execute(
        f"UPDATE voice_notes SET {', '.join(updates)} WHERE id = ?", params
    )
    await db.commit()

    cursor = await db.execute("SELECT * FROM voice_notes WHERE id = ?", (note_id,))
    row = await cursor.fetchone()
    return dict(row) if row else None


async def list_voice_notes(note_type: Optional[str] = None, status: Optional[str] = None,
                             limit: int = 50) -> list[dict]:
    """List voice notes with optional filters."""
    db = await database.get_connection()

    conditions = []
    params = []
    if note_type:
        conditions.append("note_type = ?")
        params.append(note_type)
    if status:
        conditions.append("status = ?")
        params.append(status)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    cursor = await db.execute(
        f"SELECT * FROM voice_notes {where} ORDER BY created_at DESC LIMIT ?",
        params + [limit],
    )
    return [dict(r) for r in await cursor.fetchall()]


# --- Personality Snapshot ---


async def build_personality_snapshot() -> Optional[dict]:
    """Build a compact personality snapshot for session_start.

    Returns None if no personality data exists yet.
    Returns traits, recent shifts, active preferences, voice notes, and a summary paragraph.
    """
    db = await database.get_connection()

    # All traits
    cursor = await db.execute(
        "SELECT name, value, description, category FROM personality_traits ORDER BY name"
    )
    traits = [dict(r) for r in await cursor.fetchall()]

    # Recent shifts (last 7 days)
    seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    cursor = await db.execute(
        """SELECT th.*, pt.name as trait_name
        FROM trait_history th
        JOIN personality_traits pt ON th.trait_id = pt.id
        WHERE th.created_at >= ?
        ORDER BY th.change_magnitude DESC LIMIT 3""",
        (seven_days_ago,),
    )
    recent_shifts = [dict(r) for r in await cursor.fetchall()]

    # Top preferences by strength
    cursor = await db.execute(
        "SELECT id, content, domain, strength, sentiment FROM preferences WHERE status = 'active' ORDER BY strength DESC LIMIT 10"
    )
    active_preferences = [dict(r) for r in await cursor.fetchall()]

    # Active voice notes
    cursor = await db.execute(
        "SELECT id, content, note_type FROM voice_notes WHERE status = 'active' ORDER BY updated_at DESC LIMIT 5"
    )
    active_voice_notes = [dict(r) for r in await cursor.fetchall()]

    # If nothing exists yet, return None
    if not traits and not active_preferences and not active_voice_notes:
        return None

    # Build summary paragraph
    summary = _build_personality_summary(traits, recent_shifts, active_preferences, active_voice_notes)

    return {
        "traits": traits,
        "recent_shifts": recent_shifts,
        "active_preferences": active_preferences,
        "active_voice_notes": active_voice_notes,
        "personality_summary": summary,
    }


def _build_personality_summary(traits: list[dict], shifts: list[dict],
                                preferences: list[dict], voice_notes: list[dict]) -> str:
    """Generate a natural-language personality summary."""
    parts = []

    # Trait summary
    if traits:
        trait_strs = []
        for t in traits:
            trait_strs.append(f"{t['name']} ({t['value']:.1f})")
        parts.append(f"Echo's current traits: {', '.join(trait_strs)}.")

    # Recent shifts
    if shifts:
        shift_strs = []
        for s in shifts:
            direction = "up" if s["new_value"] > s["previous_value"] else "down"
            shift_strs.append(
                f"{s['trait_name']} shifted {direction} ({s['previous_value']:.1f} -> {s['new_value']:.1f})"
            )
        parts.append(f"Recent changes: {'; '.join(shift_strs)}.")

    # Top preferences
    if preferences:
        pref_strs = [p["content"] for p in preferences[:5]]
        parts.append(f"Preferences: {'; '.join(pref_strs)}.")

    # Voice patterns
    if voice_notes:
        note_strs = [n["content"] for n in voice_notes[:3]]
        parts.append(f"Voice patterns: {'; '.join(note_strs)}.")

    return " ".join(parts) if parts else "No personality data yet."


# --- Stats ---


async def get_personality_stats() -> dict:
    """Get personality system statistics."""
    db = await database.get_connection()

    cursor = await db.execute("SELECT COUNT(*) FROM personality_traits")
    trait_count = (await cursor.fetchone())[0]

    cursor = await db.execute("SELECT COUNT(*) FROM preferences")
    preference_count = (await cursor.fetchone())[0]

    cursor = await db.execute("SELECT COUNT(*) FROM preferences WHERE status = 'active'")
    active_preference_count = (await cursor.fetchone())[0]

    cursor = await db.execute("SELECT COUNT(*) FROM voice_notes")
    voice_note_count = (await cursor.fetchone())[0]

    cursor = await db.execute("SELECT COUNT(*) FROM voice_notes WHERE status = 'active'")
    active_voice_note_count = (await cursor.fetchone())[0]

    cursor = await db.execute("SELECT COUNT(*) FROM trait_history")
    total_shifts = (await cursor.fetchone())[0]

    # Most-changed traits (by number of history entries)
    cursor = await db.execute(
        """SELECT pt.name, COUNT(th.id) as shift_count, pt.value as current_value
        FROM trait_history th
        JOIN personality_traits pt ON th.trait_id = pt.id
        GROUP BY th.trait_id
        ORDER BY shift_count DESC LIMIT 5"""
    )
    most_changed = [dict(r) for r in await cursor.fetchall()]

    # Trait stability: average magnitude of recent changes
    seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    cursor = await db.execute(
        "SELECT AVG(change_magnitude) FROM trait_history WHERE created_at >= ?",
        (seven_days_ago,),
    )
    row = await cursor.fetchone()
    recent_avg_magnitude = round(row[0], 3) if row[0] is not None else 0.0

    return {
        "trait_count": trait_count,
        "preference_count": preference_count,
        "active_preference_count": active_preference_count,
        "voice_note_count": voice_note_count,
        "active_voice_note_count": active_voice_note_count,
        "total_trait_shifts": total_shifts,
        "most_changed_traits": most_changed,
        "recent_avg_shift_magnitude": recent_avg_magnitude,
    }
