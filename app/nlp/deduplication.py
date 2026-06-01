import numpy as np
from sklearn.metrics.pairwise import cosine_similarity


def encode_alert(text, encoder):
    embedding = encoder.encode([text], show_progress_bar=False)
    return embedding[0]


def is_duplicate(new_embedding, existing_embeddings, threshold=0.85):
    best_id = None
    best_score = 0.0

    for alert_id, emb in existing_embeddings.items():
        sim = cosine_similarity([new_embedding], [emb])[0][0]
        if sim > best_score:
            best_score = sim
            best_id = alert_id

    if best_score >= threshold:
        return True, best_id, float(best_score)
    return False, best_id, float(best_score)


def deduplicate_batch(alerts, encoder, threshold=0.85):
    texts = [a["raw_text"] for a in alerts]
    embeddings = encoder.encode(texts, show_progress_bar=False)

    accumulated = {}
    results = []

    for i, alert in enumerate(alerts):
        new_emb = embeddings[i]
        duplicate, match_id, score = is_duplicate(new_emb, accumulated, threshold)
        alert["is_duplicate"] = int(duplicate)
        alert["duplicate_of"] = match_id
        alert["similarity_score"] = score
        alert["embedding"] = new_emb
        results.append(alert)
        if not duplicate:
            accumulated[alert["alert_id"]] = new_emb

    return results
