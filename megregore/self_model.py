"""Self-model predictions for Megregore. Echo makes falsifiable predictions about its own behavior."""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from . import database

logger = logging.getLogger("megregore.self_model")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def make_prediction(
    prediction: str,
    prediction_type: str = "behavioral",
    confidence: float = 0.5,
    timeframe_hours: float = 168.0,
    evaluation_criteria: dict = None,
    session_id: Optional[str] = None,
) -> dict:
    """Store a new self-prediction."""
    db = await database.get_connection()
    now = _now()

    await db.execute(
        """INSERT INTO self_predictions
           (prediction, prediction_type, confidence, timeframe_hours,
            evaluation_criteria, status, session_id, created_at)
           VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
        (
            prediction, prediction_type, confidence, timeframe_hours,
            json.dumps(evaluation_criteria or {}), session_id, now,
        ),
    )
    await db.commit()

    cursor = await db.execute("SELECT last_insert_rowid()")
    pred_id = (await cursor.fetchone())[0]

    logger.info("Self-prediction #%d created: %s (confidence=%.2f)", pred_id, prediction_type, confidence)
    return {
        "status": "predicted",
        "prediction_id": pred_id,
        "prediction_type": prediction_type,
        "confidence": confidence,
        "timeframe_hours": timeframe_hours,
        "created_at": now,
    }


async def evaluate_pending_predictions() -> dict:
    """Evaluate all predictions whose timeframe has elapsed."""
    db = await database.get_connection()
    now = _now()

    cursor = await db.execute("""
        SELECT * FROM self_predictions
        WHERE status = 'pending'
        AND datetime(created_at, '+' || CAST(CAST(timeframe_hours AS INTEGER) AS TEXT) || ' hours') <= ?
    """, (now,))
    pending = await cursor.fetchall()

    if not pending:
        return {"evaluated": 0, "verified": 0, "falsified": 0}

    results = {"evaluated": 0, "verified": 0, "falsified": 0}

    for pred in pending:
        try:
            criteria = json.loads(pred["evaluation_criteria"]) if pred["evaluation_criteria"] else {}
            outcome = await _evaluate_single(pred, criteria)

            surprise = outcome.get("surprise_score", 0.5)
            status = "verified" if outcome.get("match", False) else "falsified"

            await db.execute(
                """UPDATE self_predictions
                   SET status = ?, outcome_data = ?, surprise_score = ?, evaluated_at = ?
                   WHERE id = ?""",
                (status, json.dumps(outcome), surprise, now, pred["id"]),
            )
            results["evaluated"] += 1
            results[status] += 1

        except Exception as e:
            logger.warning("Failed to evaluate prediction #%d: %s", pred["id"], e)
            # Mark as expired if evaluation fails
            await db.execute(
                "UPDATE self_predictions SET status = 'expired', evaluated_at = ? WHERE id = ?",
                (now, pred["id"]),
            )

    await db.commit()
    logger.info(
        "Predictions evaluated: %d (verified=%d, falsified=%d)",
        results["evaluated"], results["verified"], results["falsified"],
    )
    return results


async def _evaluate_single(prediction: dict, criteria: dict) -> dict:
    """Evaluate a single prediction against actual data."""
    db = await database.get_connection()
    pred_type = prediction["prediction_type"]
    created_at = prediction["created_at"]

    if pred_type == "behavioral":
        return await _evaluate_behavioral(db, created_at, criteria)
    elif pred_type == "emotional":
        return await _evaluate_emotional(db, created_at, criteria)
    elif pred_type == "topical":
        return await _evaluate_topical(db, created_at, criteria)

    return {"match": False, "surprise_score": 0.5, "reason": "Unknown prediction type"}


async def _evaluate_behavioral(db, created_at: str, criteria: dict) -> dict:
    """Evaluate a behavioral prediction (memory type distribution)."""
    predicted_type = criteria.get("expected_dominant_type", "experience")
    predicted_ratio = criteria.get("expected_ratio", 0.5)

    cursor = await db.execute(
        "SELECT memory_type, COUNT(*) as cnt FROM memories WHERE created_at > ? GROUP BY memory_type",
        (created_at,),
    )
    rows = await cursor.fetchall()
    if not rows:
        return {"match": False, "surprise_score": 0.5, "reason": "No new memories since prediction"}

    counts = {r["memory_type"]: r["cnt"] for r in rows}
    total = sum(counts.values())
    actual_dominant = max(counts, key=counts.get)
    actual_ratio = counts.get(predicted_type, 0) / max(total, 1)

    match = actual_dominant == predicted_type or abs(actual_ratio - predicted_ratio) < 0.15
    surprise = abs(actual_ratio - predicted_ratio)

    return {
        "match": match,
        "surprise_score": round(min(1.0, surprise), 4),
        "predicted": {"type": predicted_type, "ratio": predicted_ratio},
        "actual": {"dominant_type": actual_dominant, "ratio": round(actual_ratio, 4), "counts": counts},
    }


async def _evaluate_emotional(db, created_at: str, criteria: dict) -> dict:
    """Evaluate an emotional prediction (emotional weight trends)."""
    predicted_avg = criteria.get("expected_avg_emotion", 0.0)
    thread_id = criteria.get("thread_id")

    if thread_id:
        cursor = await db.execute(
            "SELECT AVG(emotional_weight) FROM memories WHERE created_at > ? AND thread_id = ?",
            (created_at, thread_id),
        )
    else:
        cursor = await db.execute(
            "SELECT AVG(emotional_weight) FROM memories WHERE created_at > ?",
            (created_at,),
        )
    row = await cursor.fetchone()
    actual_avg = row[0] if row and row[0] is not None else 0.0

    match = abs(actual_avg - predicted_avg) < 0.2
    surprise = abs(actual_avg - predicted_avg)

    return {
        "match": match,
        "surprise_score": round(min(1.0, surprise), 4),
        "predicted": {"avg_emotion": predicted_avg},
        "actual": {"avg_emotion": round(actual_avg, 4)},
    }


async def _evaluate_topical(db, created_at: str, criteria: dict) -> dict:
    """Evaluate a topical prediction (thread activity)."""
    expected_thread = criteria.get("expected_active_thread_id")

    cursor = await db.execute(
        "SELECT thread_id, COUNT(*) as cnt FROM memories WHERE created_at > ? AND thread_id IS NOT NULL "
        "GROUP BY thread_id ORDER BY cnt DESC LIMIT 1",
        (created_at,),
    )
    row = await cursor.fetchone()
    actual_thread = row["thread_id"] if row else None
    actual_count = row["cnt"] if row else 0

    match = actual_thread == expected_thread if expected_thread else actual_count > 0
    surprise = 0.0 if match else 0.7

    return {
        "match": match,
        "surprise_score": surprise,
        "predicted": {"expected_thread": expected_thread},
        "actual": {"most_active_thread": actual_thread, "count": actual_count},
    }


async def get_prediction_accuracy(prediction_type: Optional[str] = None, limit: int = 50) -> dict:
    """Get accuracy stats for evaluated predictions."""
    db = await database.get_connection()

    if prediction_type:
        cursor = await db.execute(
            "SELECT status, surprise_score FROM self_predictions WHERE status IN ('verified', 'falsified') "
            "AND prediction_type = ? ORDER BY evaluated_at DESC LIMIT ?",
            (prediction_type, limit),
        )
    else:
        cursor = await db.execute(
            "SELECT status, surprise_score FROM self_predictions WHERE status IN ('verified', 'falsified') "
            "ORDER BY evaluated_at DESC LIMIT ?",
            (limit,),
        )
    rows = await cursor.fetchall()

    verified = sum(1 for r in rows if r["status"] == "verified")
    falsified = sum(1 for r in rows if r["status"] == "falsified")
    total = verified + falsified
    avg_surprise = sum(r["surprise_score"] or 0 for r in rows) / max(total, 1)

    return {
        "total_evaluated": total,
        "verified": verified,
        "falsified": falsified,
        "accuracy": round(verified / max(total, 1), 4),
        "avg_surprise": round(avg_surprise, 4),
    }


async def get_surprising_outcomes(min_surprise: float = 0.5, limit: int = 10) -> list[dict]:
    """Predictions that were most wrong — where real self-discovery happens."""
    db = await database.get_connection()
    cursor = await db.execute(
        """SELECT * FROM self_predictions
           WHERE status IN ('verified', 'falsified')
           AND surprise_score >= ?
           ORDER BY surprise_score DESC LIMIT ?""",
        (min_surprise, limit),
    )
    rows = await cursor.fetchall()
    results = []
    for r in rows:
        outcome = {}
        try:
            outcome = json.loads(r["outcome_data"]) if r["outcome_data"] else {}
        except json.JSONDecodeError:
            pass
        results.append({
            "id": r["id"],
            "prediction": r["prediction"],
            "prediction_type": r["prediction_type"],
            "confidence": float(r["confidence"]),
            "status": r["status"],
            "surprise_score": float(r["surprise_score"]),
            "outcome": outcome,
            "created_at": r["created_at"],
            "evaluated_at": r["evaluated_at"],
        })
    return results


async def generate_behavioral_prediction(session_id: Optional[str] = None) -> dict:
    """Auto-generate a prediction based on recent memory patterns."""
    db = await database.get_connection()

    cursor = await db.execute(
        "SELECT memory_type, COUNT(*) as cnt FROM memories "
        "ORDER BY created_at DESC LIMIT 20"
    )
    # Need to re-aggregate on the limited set
    cursor = await db.execute("""
        SELECT memory_type, COUNT(*) as cnt FROM (
            SELECT memory_type FROM memories ORDER BY created_at DESC LIMIT 20
        ) GROUP BY memory_type ORDER BY cnt DESC
    """)
    rows = await cursor.fetchall()

    if not rows:
        return {"status": "skipped", "reason": "Not enough memories for prediction"}

    dominant = rows[0]["memory_type"]
    total = sum(r["cnt"] for r in rows)
    ratio = rows[0]["cnt"] / total

    prediction_text = (
        f"Based on recent pattern ({dominant} = {ratio:.0%} of last 20 memories), "
        f"I predict my next 10 memories will be at least {max(ratio - 0.15, 0.2):.0%} {dominant} type."
    )

    return await make_prediction(
        prediction=prediction_text,
        prediction_type="behavioral",
        confidence=min(0.8, ratio),
        timeframe_hours=168.0,
        evaluation_criteria={
            "expected_dominant_type": dominant,
            "expected_ratio": round(max(ratio - 0.15, 0.2), 2),
        },
        session_id=session_id,
    )
