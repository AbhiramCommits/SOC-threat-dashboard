import hashlib
import struct

import numpy as np
import pytest

from app.nlp.deduplication import encode_alert, is_duplicate, deduplicate_batch


def _make_embedding(seed, dim=384):
    rng = np.random.default_rng(seed)
    emb = rng.normal(size=(dim,)).astype(np.float32)
    return emb / np.linalg.norm(emb)


class TestIsDuplicate:
    def test_exact_duplicate_flagged(self):
        emb = _make_embedding(42)
        existing = {"alert-a": emb, "alert-b": _make_embedding(99)}
        dup, match, score = is_duplicate(emb, existing, threshold=0.85)
        assert dup is True
        assert match == "alert-a"
        assert score == pytest.approx(1.0, abs=1e-4)

    def test_paraphrase_flagged(self):
        base = _make_embedding(42)
        noise = np.random.default_rng(1).normal(scale=0.01, size=base.shape).astype(np.float32)
        similar = (base + noise) / np.linalg.norm(base + noise)
        existing = {"alert-a": base}
        dup, match, score = is_duplicate(similar, existing, threshold=0.85)
        assert dup is True
        assert match == "alert-a"
        assert score > 0.95

    def test_unrelated_not_flagged(self):
        emb_a = _make_embedding(42)
        emb_b = _make_embedding(9999)
        existing = {"alert-a": emb_a}
        dup, match, score = is_duplicate(emb_b, existing, threshold=0.85)
        assert dup is False
        assert score < 0.85

    def test_empty_existing_returns_false(self):
        emb = _make_embedding(42)
        dup, match, score = is_duplicate(emb, {}, threshold=0.85)
        assert dup is False
        assert match is None
        assert score == 0.0


class TestDeduplicateBatch:
    def test_first_alert_not_duplicate(self):
        alerts = [
            {"alert_id": "a1", "raw_text": "C2 traffic on port 443 detected"},
        ]
        encoder = DummyEncoder(seed=10)
        result = deduplicate_batch(alerts, encoder, threshold=0.85)
        assert result[0]["is_duplicate"] == 0
        assert result[0]["duplicate_of"] is None

    def test_duplicate_within_batch_flagged(self):
        alerts = [
            {"alert_id": "a1", "raw_text": "C2 traffic on port 443 detected"},
            {"alert_id": "a2", "raw_text": "C2 traffic on port 443 detected"},
        ]
        encoder = DummyEncoder(seed=10)
        result = deduplicate_batch(alerts, encoder, threshold=0.85)
        assert result[0]["is_duplicate"] == 0
        assert result[1]["is_duplicate"] == 1
        assert result[1]["duplicate_of"] == "a1"
        assert result[1]["similarity_score"] > 0.85

    def test_paraphrase_flagged_in_batch(self):
        alerts = [
            {"alert_id": "a1", "raw_text": "C2 traffic on port 443 outbound connection to known IP detected"},
            {"alert_id": "a2", "raw_text": "C2 traffic on port 443 outbound connection to server detected"},
        ]
        encoder = DummyEncoder(seed=10)
        result = deduplicate_batch(alerts, encoder, threshold=0.85)
        assert result[0]["is_duplicate"] == 0
        assert result[1]["is_duplicate"] == 1

    def test_unrelated_not_flagged_in_batch(self):
        alerts = [
            {"alert_id": "a1", "raw_text": "C2 traffic on port 443 detected"},
            {"alert_id": "a2", "raw_text": "New user account created on domain controller"},
        ]
        encoder = DummyEncoder(seed=10)
        result = deduplicate_batch(alerts, encoder, threshold=0.85)
        assert result[0]["is_duplicate"] == 0
        assert result[1]["is_duplicate"] == 0

    def test_embeddings_populated(self):
        alerts = [
            {"alert_id": "a1", "raw_text": "C2 traffic on port 443"},
            {"alert_id": "a2", "raw_text": "Registry key modified"},
        ]
        encoder = DummyEncoder(seed=10)
        result = deduplicate_batch(alerts, encoder, threshold=0.85)
        assert result[0]["embedding"] is not None
        assert len(result[0]["embedding"]) == 384
        assert result[1]["embedding"] is not None


class DummyEncoder:
    def __init__(self, seed, dim=384):
        self.seed = seed
        self.dim = dim
        self._word_vectors = {}

    @staticmethod
    def _word_seed(word):
        digest = hashlib.sha256(word.encode()).digest()
        return struct.unpack("<I", digest[:4])[0]

    def _word_vector(self, word):
        if word not in self._word_vectors:
            rng = np.random.default_rng(self.seed + self._word_seed(word))
            self._word_vectors[word] = rng.normal(size=(self.dim,)).astype(np.float32)
        return self._word_vectors[word]

    def encode(self, texts, show_progress_bar=False):
        out = []
        for text in texts:
            tokens = text.lower().replace("-", " ").split()
            if not tokens:
                emb = np.zeros(self.dim, dtype=np.float32)
            else:
                emb = sum(self._word_vector(t) for t in tokens) / len(tokens)
            norm = np.linalg.norm(emb)
            out.append(emb / norm if norm > 0 else emb)
        return np.stack(out)
