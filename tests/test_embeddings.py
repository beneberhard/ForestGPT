import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.rag import index


class EmbeddingTests(unittest.TestCase):
    def document(self, vectors):
        return SimpleNamespace(
            id=1,
            metadata_json={**index.embedding_metadata(), "sha256": "example"},
            chunks=[SimpleNamespace(id=i, chunk_text="forest", embedding=v) for i, v in enumerate(vectors)],
        )

    def test_metadata_alone_does_not_mean_indexed(self):
        for vectors in ([], [None], [[]], [[1.0], None]):
            with self.subTest(vectors=vectors):
                self.assertFalse(index.document_has_current_embedding(self.document(vectors)))
        self.assertTrue(index.document_has_current_embedding(self.document([[1.0]])))

    def test_duplicate_without_vectors_is_not_skipped(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [self.document([None])]
        self.assertFalse(index.document_with_hash_exists(db, "example", current_embedding_only=True))
        self.assertTrue(index.document_with_hash_exists(db, "example"))

    def test_unsupported_provider_is_explicit(self):
        index._embedding_client.cache_clear()
        try:
            with patch.object(index, "EMBEDDING_PROVIDER", "huggingface"):
                with self.assertRaisesRegex(ValueError, "Unsupported EMBEDDING_PROVIDER"):
                    index._embedding_client()
        finally:
            index._embedding_client.cache_clear()

    def test_api_failure_logs_fallback(self):
        client = MagicMock()
        client.embeddings.create.side_effect = RuntimeError("failure")
        with patch.object(index, "_embedding_client", return_value=client):
            with self.assertLogs(index.logger, level="WARNING"):
                self.assertIsNone(index.embed_text("forest"))

    def test_repair_orders_vectors_and_preserves_text(self):
        document = self.document([None, None])
        db = MagicMock()
        db.query.return_value.order_by.return_value.all.return_value = [document]
        client = MagicMock()
        client.embeddings.create.return_value.data = [
            SimpleNamespace(index=1, embedding=[0.2]),
            SimpleNamespace(index=0, embedding=[0.1]),
        ]
        with patch.object(index, "_embedding_client", return_value=client):
            result = index.repair_document_embeddings(db)
        self.assertEqual(result["chunks_updated"], 2)
        self.assertEqual([c.embedding for c in document.chunks], [[0.1], [0.2]])
        self.assertEqual([c.chunk_text for c in document.chunks], ["forest", "forest"])
        db.commit.assert_called_once()

    def test_incomplete_batch_rolls_back(self):
        db = MagicMock()
        db.query.return_value.order_by.return_value.all.return_value = [self.document([None])]
        client = MagicMock()
        client.embeddings.create.return_value.data = []
        with patch.object(index, "_embedding_client", return_value=client):
            with self.assertRaisesRegex(ValueError, "incomplete batch"):
                index.repair_document_embeddings(db)
        db.rollback.assert_called_once()
        db.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
