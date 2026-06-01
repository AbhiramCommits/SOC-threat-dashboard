import pickle
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone


def init_db(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            alert_id       TEXT PRIMARY KEY,
            timestamp      TEXT NOT NULL,
            raw_text       TEXT NOT NULL,
            tactic_category TEXT,
            confidence_score REAL,
            is_duplicate   INTEGER DEFAULT 0,
            embedding      BLOB
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_alerts_tactic ON alerts(tactic_category)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp)
    """)
    conn.commit()
    return conn


def insert_alert(conn, alert_dict):
    embedding = alert_dict.get("embedding")
    if embedding is not None:
        embedding = pickle.dumps(embedding)
    conn.execute(
        """
        INSERT OR REPLACE INTO alerts
            (alert_id, timestamp, raw_text, tactic_category, confidence_score, is_duplicate, embedding)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            alert_dict["alert_id"],
            alert_dict["timestamp"],
            alert_dict["raw_text"],
            alert_dict.get("tactic_category"),
            alert_dict.get("confidence_score"),
            alert_dict.get("is_duplicate", 0),
            embedding,
        ),
    )
    conn.commit()


def get_alerts(conn, tactic=None, duplicate=None, limit=50, offset=0):
    query = "SELECT alert_id, timestamp, raw_text, tactic_category, confidence_score, is_duplicate FROM alerts WHERE 1=1"
    params = []

    if tactic is not None:
        query += " AND tactic_category = ?"
        params.append(tactic)
    if duplicate is not None:
        query += " AND is_duplicate = ?"
        params.append(int(duplicate))

    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    columns = ["alert_id", "timestamp", "raw_text", "tactic_category", "confidence_score", "is_duplicate"]
    return [dict(zip(columns, row)) for row in rows]


def get_alert_by_id(conn, alert_id):
    row = conn.execute(
        "SELECT alert_id, timestamp, raw_text, tactic_category, confidence_score, is_duplicate FROM alerts WHERE alert_id = ?",
        (alert_id,),
    ).fetchone()
    if row is None:
        return None
    columns = ["alert_id", "timestamp", "raw_text", "tactic_category", "confidence_score", "is_duplicate"]
    return dict(zip(columns, row))


def get_stats(conn):
    # tactic distribution
    tactic_rows = conn.execute(
        "SELECT tactic_category, COUNT(*) as cnt FROM alerts GROUP BY tactic_category ORDER BY cnt DESC"
    ).fetchall()
    tactic_distribution = {row[0] if row[0] else "unknown": row[1] for row in tactic_rows}

    # duplicate rate
    total = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
    duplicates = conn.execute("SELECT COUNT(*) FROM alerts WHERE is_duplicate = 1").fetchone()[0]
    duplicate_rate = (duplicates / total) if total > 0 else 0.0

    # daily volume for last 7 days
    today = datetime.now(timezone.utc).date()
    daily_volume = {}
    for i in range(6, -1, -1):
        day = (today - timedelta(days=i)).isoformat()
        count = conn.execute(
            "SELECT COUNT(*) FROM alerts WHERE date(timestamp) = ?", (day,)
        ).fetchone()[0]
        daily_volume[day] = count

    return {
        "tactic_distribution": tactic_distribution,
        "duplicate_rate": duplicate_rate,
        "daily_volume": daily_volume,
    }
