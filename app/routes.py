import pickle
import uuid
from datetime import datetime, timezone

import numpy as np
from flask import Blueprint, current_app, g, jsonify, render_template, request

from app.models import get_alert_by_id, get_alerts, get_stats, insert_alert
from app.nlp.classifier import predict_tactic
from app.nlp.deduplication import is_duplicate, encode_alert
from app.nlp.embeddings import load_all_embeddings, load_encoder, store_embedding

api_bp = Blueprint("api", __name__)


def get_db():
    if "db" not in g:
        g.db = current_app.config["DB_CONN"]
    return g.db


def get_tfidf_model():
    return current_app.config.get("TFIDF_MODEL")


def _parse_stix_bundle(bundle):
    metadata = bundle.get("metadata", {})
    raw_text = metadata.get("raw_text")
    tactic = metadata.get("tactic")
    timestamp = metadata.get("timestamp")
    alert_id = None

    if not raw_text:
        for obj in bundle.get("objects", []):
            if obj.get("type") == "indicator":
                raw_text = obj.get("description", "")
                alert_id = obj.get("id")
                if not tactic and obj.get("labels"):
                    tactic = obj["labels"][0]
                if not timestamp:
                    timestamp = obj.get("created")
                break

    if not alert_id:
        alert_id = f"indicator--{uuid.uuid4()}"
    if not timestamp:
        timestamp = datetime.now(timezone.utc).isoformat()
    if not raw_text:
        raw_text = ""

    return alert_id, timestamp, raw_text, tactic


def _extract_top_features(model, text, predicted_tactic, n=3):
    vectorizer = model.named_steps["tfidf"]
    classifier = model.named_steps["clf"]
    class_idx = list(classifier.classes_).index(predicted_tactic)
    tfidf_vec = vectorizer.transform([text]).toarray()[0]
    coef = classifier.coef_[class_idx]
    weighted = tfidf_vec * coef
    top_indices = np.argsort(weighted)[::-1][:n]
    feature_names = vectorizer.get_feature_names_out()
    return [
        {"feature": str(feature_names[i]), "weight": float(weighted[i])}
        for i in top_indices
        if weighted[i] != 0
    ]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@api_bp.route("/")
def dashboard():
    return render_template("dashboard.html")


@api_bp.route("/api/alerts", methods=["GET"])
def list_alerts():
    db = get_db()
    tactic = request.args.get("tactic")
    duplicate_raw = request.args.get("duplicate")
    search = request.args.get("search")
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")

    duplicate = None
    if duplicate_raw is not None:
        try:
            duplicate = int(duplicate_raw)
        except ValueError:
            return jsonify({"error": "duplicate must be 0 or 1"}), 400

    try:
        page = int(request.args.get("page", 1))
        limit = int(request.args.get("limit", 50))
    except ValueError:
        return jsonify({"error": "page and limit must be integers"}), 400

    if page < 1:
        page = 1
    if limit < 1:
        limit = 50

    offset = (page - 1) * limit
    count_row = db.execute("SELECT COUNT(*) FROM alerts").fetchone()
    total = count_row[0] if count_row else 0
    alerts = get_alerts(
        db,
        tactic=tactic,
        duplicate=duplicate,
        search=search,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )

    return jsonify({"data": alerts, "page": page, "limit": limit, "total": total})


@api_bp.route("/api/ingest", methods=["POST"])
def ingest():
    db = get_db()
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    bundles = body if isinstance(body, list) else [body]
    if not bundles:
        return jsonify({"error": "No bundles provided"}), 400

    tfidf_model = get_tfidf_model()
    threshold = current_app.config.get("SIMILARITY_THRESHOLD", 0.85)

    # load existing embeddings for deduplication
    existing_embeddings = load_all_embeddings(db)

    ingested = 0
    duplicates = 0
    errors = 0
    parsed_alerts = []

    for bundle in bundles:
        try:
            alert_id, timestamp, raw_text, tactic = _parse_stix_bundle(bundle)

            if not raw_text.strip():
                errors += 1
                continue

            # classify tactic
            if tfidf_model:
                predicted_tactic, confidence = predict_tactic(tfidf_model, raw_text, "tfidf")
            else:
                predicted_tactic = tactic or "unknown"
                confidence = 0.0

            # encode and deduplicate
            try:
                encoder = load_encoder()
                embedding = encode_alert(raw_text, encoder)
                dup, match_id, score = is_duplicate(embedding, existing_embeddings, threshold)
            except Exception:
                embedding = None
                dup, match_id, score = False, None, 0.0

            alert_dict = {
                "alert_id": alert_id,
                "timestamp": timestamp,
                "raw_text": raw_text,
                "tactic_category": predicted_tactic,
                "confidence_score": round(confidence, 4),
                "is_duplicate": int(dup),
            }

            insert_alert(db, alert_dict)
            if embedding is not None:
                store_embedding(db, alert_id, embedding)

            if not dup and embedding is not None:
                existing_embeddings[alert_id] = embedding

            alert_dict["duplicate_of"] = match_id
            alert_dict["similarity_score"] = round(score, 4)
            parsed_alerts.append(alert_dict)

            ingested += 1
            if dup:
                duplicates += 1

        except Exception as exc:
            errors += 1
            parsed_alerts.append({"error": str(exc)})

    return jsonify(
        {
            "ingested": ingested,
            "duplicates": duplicates,
            "errors": errors,
            "total": len(bundles),
            "alerts": parsed_alerts,
        }
    ), 201


@api_bp.route("/api/stats", methods=["GET"])
def stats():
    db = get_db()
    return jsonify(get_stats(db))


@api_bp.route("/api/alert/<alert_id>", methods=["GET"])
def alert_detail(alert_id):
    db = get_db()
    alert = get_alert_by_id(db, alert_id)
    if alert is None:
        return jsonify({"error": "Alert not found"}), 404

    tfidf_model = get_tfidf_model()
    if tfidf_model and alert.get("raw_text") and alert.get("tactic_category"):
        features = _extract_top_features(
            tfidf_model, alert["raw_text"], alert["tactic_category"], n=3
        )
    else:
        features = []

    alert["top_features"] = features
    return jsonify(alert)
