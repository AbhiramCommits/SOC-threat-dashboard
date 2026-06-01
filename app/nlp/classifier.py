import pickle

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.pipeline import Pipeline

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

_sentence_transformer = None


def _get_sentence_transformer():
    global _sentence_transformer
    if _sentence_transformer is None:
        from sentence_transformers import SentenceTransformer

        _sentence_transformer = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _sentence_transformer


def train_tfidf_classifier(texts, labels):
    pipeline = Pipeline(
        [
            ("tfidf", TfidfVectorizer(max_features=5000, ngram_range=(1, 2))),
            ("clf", LogisticRegression(max_iter=1000)),
        ]
    )
    pipeline.fit(texts, labels)
    return pipeline


def train_embedding_classifier(texts, labels):
    encoder = _get_sentence_transformer()
    embeddings = encoder.encode(texts, show_progress_bar=False)
    clf = LogisticRegression(max_iter=1000)
    clf.fit(embeddings, labels)
    return {"encoder": encoder, "clf": clf}


def predict_tactic(model, text, method):
    if method == "tfidf":
        probs = model.predict_proba([text])[0]
        predicted = model.predict([text])[0]
    elif method == "embedding":
        embeddings = model["encoder"].encode([text], show_progress_bar=False)
        probs = model["clf"].predict_proba(embeddings)[0]
        predicted = model["clf"].predict(embeddings)[0]
    else:
        raise ValueError(f"Unknown method: {method}")
    confidence = float(np.max(probs))
    return predicted, confidence


def compare_classifiers(X_test, y_test, tfidf_model, embed_model):
    # TF-IDF predictions
    tfidf_preds = tfidf_model.predict(X_test)
    tfidf_report = classification_report(y_test, tfidf_preds, output_dict=True, zero_division=0)
    tfidf_cm = confusion_matrix(y_test, tfidf_preds)

    # Embedding predictions
    encoder = embed_model["encoder"]
    X_test_embed = encoder.encode(X_test, show_progress_bar=False)
    embed_preds = embed_model["clf"].predict(X_test_embed)
    embed_report = classification_report(y_test, embed_preds, output_dict=True, zero_division=0)
    embed_cm = confusion_matrix(y_test, embed_preds)

    print("=" * 60)
    print("TF-IDF + Logistic Regression")
    print("=" * 60)
    print(classification_report(y_test, tfidf_preds, zero_division=0))

    print("=" * 60)
    print("Sentence-Transformer Embedding + Logistic Regression")
    print("=" * 60)
    print(classification_report(y_test, embed_preds, zero_division=0))

    return {
        "tfidf": {"report": tfidf_report, "confusion_matrix": tfidf_cm},
        "embedding": {"report": embed_report, "confusion_matrix": embed_cm},
    }
