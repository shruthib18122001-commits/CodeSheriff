from unittest.mock import MagicMock

from app.services import llm


def test_embed_text_returns_vector(monkeypatch):
    fake_client = MagicMock()
    fake_client.embeddings.create.return_value = MagicMock(data=[MagicMock(embedding=[0.1, 0.2, 0.3])])
    monkeypatch.setattr(llm, "_openai", lambda: fake_client)

    result = llm.embed_text("some code")

    assert result == [0.1, 0.2, 0.3]
    fake_client.embeddings.create.assert_called_once()


def test_embed_text_substitutes_blank_input(monkeypatch):
    fake_client = MagicMock()
    fake_client.embeddings.create.return_value = MagicMock(data=[MagicMock(embedding=[0.0])])
    monkeypatch.setattr(llm, "_openai", lambda: fake_client)

    llm.embed_text("")

    _, kwargs = fake_client.embeddings.create.call_args
    assert kwargs["input"] == " "


def test_search_chunks_orders_by_cosine_distance_and_limits(fake_db):
    llm.search_chunks(fake_db, "repo-1", [0.1, 0.2], top_k=5)

    fake_db.query.assert_called_once()
    fake_db.query.return_value.filter.return_value.order_by.return_value.limit.assert_called_once_with(5)


def test_ask_codebase_returns_placeholder_when_no_chunks():
    result = llm.ask_codebase("where is auth?", [])

    assert result["sources"] == []
    assert "couldn't find" in result["answer"].lower()


def test_ask_codebase_builds_grounded_answer_with_sources(monkeypatch):
    chunk = MagicMock(
        file_path="auth.py", start_line=1, end_line=10, symbol_name="login", chunk_type="function", content="def login(): ..."
    )

    fake_client = MagicMock()
    fake_text_block = MagicMock(type="text", text="Auth is handled in auth.py:login.")
    fake_client.messages.create.return_value = MagicMock(content=[fake_text_block])
    monkeypatch.setattr(llm, "_anthropic", lambda: fake_client)

    result = llm.ask_codebase("where is auth handled?", [chunk])

    assert result["answer"] == "Auth is handled in auth.py:login."
    assert result["sources"] == [{"file_path": "auth.py", "start_line": 1, "end_line": 10, "symbol_name": "login"}]


def test_ask_codebase_falls_back_gracefully_on_anthropic_error(monkeypatch):
    chunk = MagicMock(file_path="auth.py", start_line=1, end_line=10, symbol_name="login", chunk_type="function", content="...")

    fake_client = MagicMock()
    fake_client.messages.create.side_effect = RuntimeError("anthropic is down")
    monkeypatch.setattr(llm, "_anthropic", lambda: fake_client)

    result = llm.ask_codebase("where is auth handled?", [chunk])

    assert "temporarily unavailable" in result["answer"].lower()


def test_raw_completion_concatenates_text_blocks(monkeypatch):
    fake_client = MagicMock()
    fake_client.messages.create.return_value = MagicMock(
        content=[MagicMock(type="text", text="hello "), MagicMock(type="text", text="world")]
    )
    monkeypatch.setattr(llm, "_anthropic", lambda: fake_client)

    assert llm.raw_completion("prompt") == "hello world"
