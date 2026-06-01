import pickle

import numpy as np

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

_encoder = None


def load_encoder():
    global _encoder
    if _encoder is None:
        from sentence_transformers import SentenceTransformer

        _encoder = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _encoder


def store_embedding(conn, alert_id, embedding):
    blob = pickle.dumps(embedding)
    conn.execute("UPDATE alerts SET embedding = ? WHERE alert_id = ?", (blob, alert_id))
    conn.commit()


def load_all_embeddings(conn):
    rows = conn.execute("SELECT alert_id, embedding FROM alerts WHERE embedding IS NOT NULL").fetchall()
    return {row[0]: pickle.loads(row[1]) for row in rows}
