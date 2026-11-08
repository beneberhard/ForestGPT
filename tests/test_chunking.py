import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from app.geo.models import Document, DocumentChunk
from app.llm.service import _compact_chunk
from app.rag import index


class TokenChunkingTests(unittest.TestCase):
    def test_token_limit_overlap_and_full_coverage(self):
        encoding = index._chunk_tokenizer()
        text = "Forests provide habitat and support biodiversity. " * 400
        tokens = encoding.encode_ordinary(text)
        chunks = index.chunk_text(text)
        encoded = [encoding.encode_ordinary(chunk) for chunk in chunks]
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 600 for chunk in encoded))
        rebuilt = encoded[0][:]
        for left, right in zip(encoded, encoded[1:]):
            self.assertEqual(left[-90:], right[:90])
            rebuilt.extend(right[90:])
        self.assertEqual(rebuilt, tokens)

    def test_multilingual_text_does_not_split_unicode_characters(self):
        text = "Wälder, Ökologie, cambiamento climatico, 森林 🌲🌳 — biodiversity. " * 300
        encoding = index._chunk_tokenizer()
        chunks = index.chunk_text(text)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertNotIn("\ufffd", chunk)
            self.assertIn(chunk, text)
            self.assertLessEqual(len(encoding.encode_ordinary(chunk)), 600)
        self.assertTrue(text.startswith(chunks[0]))
        self.assertTrue(text.endswith(chunks[-1]))

    def test_literal_special_tokens_are_plain_text(self):
        text = "A document may mention <|endoftext|> literally."
        self.assertEqual(index.chunk_text(text), [text])

    def test_empty_text_and_invalid_parameters(self):
        self.assertEqual(index.chunk_text(" \n\t"), [])
        for size, overlap in [(0, 0), (10, 10), (10, -1)]:
            with self.assertRaises(ValueError):
                index.chunk_text("forest", chunk_size=size, overlap=overlap)

    def test_full_chunk_reaches_prompt_context(self):
        text = "Evidence about forest management. " * 100 + "CRITICAL END EVIDENCE"
        result = _compact_chunk({"title": "Study", "score": 0.8, "chunk_text": text})
        self.assertEqual(result["chunk_text"], text)
        self.assertTrue(result["chunk_text"].endswith("CRITICAL END EVIDENCE"))

    def test_reingestion_preserves_document_id_and_records_token_settings(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "study.txt"
            path.write_text("Forest research and biodiversity. " * 300)
            existing = Document(id=7, title="Old", source_path=str(path), metadata_json={})
            existing.chunks = [DocumentChunk(chunk_text="Old text", embedding=[1.0])]
            db = MagicMock()
            db.query.return_value.filter.return_value.first.return_value = existing
            with patch.object(index, "embed_texts", side_effect=lambda texts: [[0.1] for _ in texts]):
                result = index.ingest_document_file(db, path, replace=True, commit=False)
            self.assertEqual(existing.id, 7)
            self.assertTrue(index.document_has_current_chunking(existing))
            self.assertGreater(result["chunks_created"], 1)
            new_chunks = [call.args[0] for call in db.add.call_args_list if isinstance(call.args[0], DocumentChunk)]
            self.assertEqual(len(new_chunks), result["chunks_created"])
            self.assertTrue(all(chunk.metadata_json["token_count"] <= 600 for chunk in new_chunks))
            db.commit.assert_not_called()

    def test_embedding_failure_does_not_clear_existing_chunks(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "study.txt"
            path.write_text("Forest research")
            existing = Document(id=7, title="Old", source_path=str(path), metadata_json={})
            existing.chunks = [DocumentChunk(chunk_text="Old text", embedding=[1.0])]
            db = MagicMock()
            db.query.return_value.filter.return_value.first.return_value = existing
            with patch.object(index, "embed_texts", side_effect=RuntimeError("API unavailable")):
                with self.assertRaises(RuntimeError):
                    index.ingest_document_file(db, path, replace=True)
            self.assertEqual(existing.chunks[0].chunk_text, "Old text")
            db.commit.assert_not_called()

    def test_old_chunk_settings_force_reingestion_even_with_vectors(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "study.txt"
            path.write_text("Forest research")
            metadata = {**index.embedding_metadata(), "sha256": index.file_sha256(path)}
            existing = Document(id=7, title="Old", source_path=str(path), metadata_json=metadata)
            existing.chunks = [DocumentChunk(chunk_text="Old text", embedding=[1.0])]
            db = MagicMock()
            db.query.return_value.filter.return_value.first.return_value = existing
            with patch.object(index, "embed_texts", return_value=[[0.1]]) as embed:
                result = index.ingest_document_file(db, path, commit=False)
            embed.assert_called_once()
            self.assertEqual(result["documents_ingested"], 1)

    def test_pruning_only_removes_missing_files_from_corpus_directory(self):
        with TemporaryDirectory() as directory:
            corpus = Path(directory)
            path = corpus / "current.txt"
            path.write_text("Forest")
            current = Document(source_path=str(path))
            missing = Document(source_path=str(corpus / "removed.pdf"))
            outside = Document(source_path=str(corpus.parent / "elsewhere.pdf"))
            seed = Document(source_path="seeded://sample-thinning-guidance")
            db = MagicMock()
            db.query.return_value.all.return_value = [current, missing, outside, seed]
            with patch.object(index, "ingest_document_file", return_value=index._ingest_result(ingested=1)):
                result = index.ingest_corpus(db, corpus, prune_missing=True)
            db.delete.assert_called_once_with(missing)
            self.assertEqual(result["documents_removed"], 1)


if __name__ == "__main__":
    unittest.main()
