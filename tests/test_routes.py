import json
import pickle
import sqlite3
import uuid
from datetime import datetime, timezone

import numpy as np
import pytest

from app import create_app
from app.models import init_db


@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    app.config["SIMILARITY_THRESHOLD"] = 0.85

    # Use in-memory DB for tests
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_tactic ON alerts(tactic_category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp)")
    conn.commit()
    app.config["DB_CONN"] = conn

    # Train a lightweight TF-IDF model from STIX feed
    with open(app.config["STIX_FEED_PATH"]) as f:
        bundles = json.load(f)
    texts = [b["metadata"]["raw_text"] for b in bundles]
    labels = [b["metadata"]["tactic"] for b in bundles]
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline

    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(max_features=5000, ngram_range=(1, 2))),
        ("clf", LogisticRegression(max_iter=1000)),
    ])
    pipeline.fit(texts, labels)
    app.config["TFIDF_MODEL"] = pipeline

    yield app

    conn.close()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def sample_bundle():
    return {
        "type": "bundle",
        "id": f"bundle--{uuid.uuid4()}",
        "objects": [
            {
                "type": "indicator",
                "spec_version": "2.1",
                "id": f"indicator--{uuid.uuid4()}",
                "created": datetime.now(timezone.utc).isoformat(),
                "modified": datetime.now(timezone.utc).isoformat(),
                "name": "Test alert",
                "description": "Detected outbound traffic to known C2 IP over port 443",
                "indicator_types": ["malicious-activity"],
                "labels": ["command-and-control"],
                "pattern": "[file:hashes.'SHA-256' = 'abcdef123456']",
                "pattern_type": "stix",
                "valid_from": datetime.now(timezone.utc).isoformat(),
            }
        ],
        "metadata": {
            "raw_text": "Detected outbound traffic to known C2 IP over port 443",
            "tactic": "command-and-control",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }


class TestGetAlerts:
    def test_returns_empty_list(self, client):
        resp = client.get("/api/alerts")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"] == []
        assert data["total"] == 0
        assert data["page"] == 1

    def test_returns_paginated_alerts(self, client, app):
        conn = app.config["DB_CONN"]
        for i in range(5):
            conn.execute(
                "INSERT INTO alerts (alert_id, timestamp, raw_text, tactic_category, confidence_score, is_duplicate) VALUES (?, ?, ?, ?, ?, ?)",
                (f"alert-{i}", datetime.now(timezone.utc).isoformat(), f"test alert {i}", "execution", 0.9, 0),
            )
        conn.commit()

        resp = client.get("/api/alerts?limit=3&page=1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["page"] == 1
        assert data["limit"] == 3
        assert data["total"] == 5
        assert len(data["data"]) == 3

    def test_filters_by_tactic(self, client, app):
        conn = app.config["DB_CONN"]
        conn.execute(
            "INSERT INTO alerts (alert_id, timestamp, raw_text, tactic_category) VALUES (?, ?, ?, ?)",
            ("a1", datetime.now(timezone.utc).isoformat(), "c2 traffic", "command-and-control"),
        )
        conn.execute(
            "INSERT INTO alerts (alert_id, timestamp, raw_text, tactic_category) VALUES (?, ?, ?, ?)",
            ("a2", datetime.now(timezone.utc).isoformat(), "phishing", "initial-access"),
        )
        conn.commit()

        resp = client.get("/api/alerts?tactic=command-and-control")
        data = resp.get_json()
        assert len(data["data"]) == 1
        assert data["data"][0]["tactic_category"] == "command-and-control"

    def test_filters_by_duplicate(self, client, app):
        conn = app.config["DB_CONN"]
        conn.execute(
            "INSERT INTO alerts (alert_id, timestamp, raw_text, is_duplicate) VALUES (?, ?, ?, ?)",
            ("a1", datetime.now(timezone.utc).isoformat(), "dup", 1),
        )
        conn.execute(
            "INSERT INTO alerts (alert_id, timestamp, raw_text, is_duplicate) VALUES (?, ?, ?, ?)",
            ("a2", datetime.now(timezone.utc).isoformat(), "clean", 0),
        )
        conn.commit()

        resp = client.get("/api/alerts?duplicate=1")
        data = resp.get_json()
        assert len(data["data"]) == 1
        assert data["data"][0]["is_duplicate"] == 1

    def test_invalid_params_return_400(self, client):
        resp = client.get("/api/alerts?page=abc")
        assert resp.status_code == 400
        assert "error" in resp.get_json()


class TestPostIngest:
    def test_ingest_single_bundle(self, client, sample_bundle):
        resp = client.post("/api/ingest", json=sample_bundle)
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["ingested"] == 1
        assert data["total"] == 1
        assert len(data["alerts"]) == 1

        alert = data["alerts"][0]
        assert "alert_id" in alert
        assert alert["raw_text"] == sample_bundle["metadata"]["raw_text"]

    def test_ingest_bundle_list(self, client, sample_bundle):
        b2 = dict(sample_bundle)
        b2["metadata"]["raw_text"] = "Suspicious PowerShell execution detected"
        resp = client.post("/api/ingest", json=[sample_bundle, b2])
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["ingested"] == 2
        assert data["total"] == 2

    def test_ingest_empty_body(self, client):
        resp = client.post("/api/ingest", json={})
        assert resp.status_code == 400
        assert "error" in resp.get_json()

    def test_ingest_invalid_json(self, client):
        resp = client.post("/api/ingest", data="not json", content_type="application/json")
        assert resp.status_code == 400

    def test_duplicate_detection(self, client, sample_bundle):
        client.post("/api/ingest", json=sample_bundle)
        resp = client.post("/api/ingest", json=sample_bundle)
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["ingested"] == 1
        assert "duplicates" in data


class TestGetStats:
    def test_returns_stats_format(self, client, app):
        conn = app.config["DB_CONN"]
        conn.execute(
            "INSERT INTO alerts (alert_id, timestamp, raw_text, tactic_category, is_duplicate) VALUES (?, ?, ?, ?, ?)",
            ("a1", datetime.now(timezone.utc).isoformat(), "test", "execution", 0),
        )
        conn.commit()

        resp = client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "tactic_distribution" in data
        assert "duplicate_rate" in data
        assert "daily_volume" in data
        assert isinstance(data["tactic_distribution"], dict)
        assert isinstance(data["daily_volume"], dict)

    def test_empty_stats(self, client):
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["duplicate_rate"] == 0.0


class TestGetAlertDetail:
    def test_returns_alert_with_features(self, client, app):
        conn = app.config["DB_CONN"]
        alert_id = "alert-test-1"
        conn.execute(
            "INSERT INTO alerts (alert_id, timestamp, raw_text, tactic_category, confidence_score) VALUES (?, ?, ?, ?, ?)",
            (alert_id, datetime.now(timezone.utc).isoformat(), "Detected C2 traffic on port 443", "command-and-control", 0.95),
        )
        conn.commit()

        resp = client.get(f"/api/alert/{alert_id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["alert_id"] == alert_id
        assert data["tactic_category"] == "command-and-control"
        assert "top_features" in data
        assert len(data["top_features"]) <= 3

    def test_unknown_alert_returns_404(self, client):
        resp = client.get("/api/alert/nonexistent-id")
        assert resp.status_code == 404
        assert "error" in resp.get_json()
