from unittest.mock import MagicMock

from app.services import embedder


def make_chunk(content: str = "def foo(): pass"):
    chunk = MagicMock()
    chunk.content = content
    chunk.embedding = None
    return chunk


def test_embed_repo_chunks_batches_embeds_and_builds_index(fake_db, monkeypatch):
    chunks = [make_chunk(f"chunk {i}") for i in range(3)]
    fake_db.query.return_value.filter.return_value.all.return_value = chunks

    fake_client = MagicMock()
    fake_client.embeddings.create.return_value = MagicMock(data=[MagicMock(embedding=[float(i)]) for i in range(3)])
    monkeypatch.setattr(embedder, "_get_client", lambda: fake_client)

    embedder.embed_repo_chunks(fake_db, "repo-1")

    for i, chunk in enumerate(chunks):
        assert chunk.embedding == [float(i)]
    fake_db.execute.assert_called_once()  # HNSW index creation, after embeddings are populated


def test_embed_repo_chunks_is_noop_when_nothing_pending(fake_db, monkeypatch):
    fake_db.query.return_value.filter.return_value.all.return_value = []
    create_index_mock = MagicMock()
    monkeypatch.setattr(embedder, "_create_hnsw_index", create_index_mock)

    embedder.embed_repo_chunks(fake_db, "repo-1")

    create_index_mock.assert_not_called()


def test_embed_repo_chunks_skips_failed_batch_without_raising(fake_db, monkeypatch):
    chunks = [make_chunk("chunk")]
    fake_db.query.return_value.filter.return_value.all.return_value = chunks

    def boom(texts):
        raise RuntimeError("openai is down")

    monkeypatch.setattr(embedder, "_embed_batch", boom)

    # A failed embedding batch must not crash the ingestion worker.
    embedder.embed_repo_chunks(fake_db, "repo-1")

    assert chunks[0].embedding is None


def test_embed_batch_substitutes_blank_chunks(monkeypatch):
    fake_client = MagicMock()
    fake_client.embeddings.create.return_value = MagicMock(data=[MagicMock(embedding=[1.0])])
    monkeypatch.setattr(embedder, "_get_client", lambda: fake_client)

    embedder._embed_batch([""])

    _, kwargs = fake_client.embeddings.create.call_args
    assert kwargs["input"] == [" "]
