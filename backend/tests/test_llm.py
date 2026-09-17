import base64
from unittest.mock import MagicMock

from app.services import llm


def test_embed_text_returns_vector(monkeypatch):
    fake_client = MagicMock()
    fake_client.models.embed_content.return_value = MagicMock(
        embeddings=[MagicMock(values=[0.1, 0.2, 0.3])]
    )
    monkeypatch.setattr(llm, "_gemini", lambda: fake_client)

    result = llm.embed_text("some code")

    assert result == [0.1, 0.2, 0.3]
    fake_client.models.embed_content.assert_called_once()


def test_embed_text_substitutes_blank_input(monkeypatch):
    fake_client = MagicMock()
    fake_client.models.embed_content.return_value = MagicMock(
        embeddings=[MagicMock(values=[0.0])]
    )
    monkeypatch.setattr(llm, "_gemini", lambda: fake_client)

    llm.embed_text("")

    _, kwargs = fake_client.models.embed_content.call_args
    assert kwargs["contents"] == " "


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
    fake_client.models.generate_content.return_value = MagicMock(text="Auth is handled in auth.py:login.")
    monkeypatch.setattr(llm, "_gemini", lambda: fake_client)

    result = llm.ask_codebase("where is auth handled?", [chunk])

    assert result["answer"] == "Auth is handled in auth.py:login."
    assert result["sources"] == [{"file_path": "auth.py", "start_line": 1, "end_line": 10, "symbol_name": "login"}]


def test_ask_codebase_passes_thinking_level_to_generation_config(monkeypatch):
    chunk = MagicMock(file_path="auth.py", start_line=1, end_line=10, symbol_name="login", chunk_type="function", content="...")

    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = MagicMock(text="answer")
    monkeypatch.setattr(llm, "_gemini", lambda: fake_client)

    llm.ask_codebase("where is auth handled?", [chunk], thinking_level="high")

    _, kwargs = fake_client.models.generate_content.call_args
    assert kwargs["config"].thinking_config.thinking_level.value == "HIGH"
    assert kwargs["config"].max_output_tokens == 3000


def test_ask_codebase_rejects_invalid_thinking_level(monkeypatch):
    chunk = MagicMock(file_path="auth.py", start_line=1, end_line=10, symbol_name="login", chunk_type="function", content="...")
    monkeypatch.setattr(llm, "_gemini", lambda: MagicMock())

    result = llm.ask_codebase("q", [chunk], thinking_level="extreme")

    assert "temporarily unavailable" in result["answer"].lower()


def test_ask_codebase_includes_attachments_as_parts(monkeypatch):
    chunk = MagicMock(file_path="auth.py", start_line=1, end_line=10, symbol_name="login", chunk_type="function", content="...")
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = MagicMock(text="answer")
    monkeypatch.setattr(llm, "_gemini", lambda: fake_client)

    image_bytes = b"fake-png-bytes"
    attachments = [{"filename": "error.png", "mime_type": "image/png", "data": base64.b64encode(image_bytes).decode()}]

    llm.ask_codebase("what does this error mean?", [chunk], attachments=attachments)

    _, kwargs = fake_client.models.generate_content.call_args
    contents = kwargs["contents"]
    assert len(contents) == 2
    assert contents[1].inline_data.data == image_bytes
    assert contents[1].inline_data.mime_type == "image/png"


def test_ask_codebase_answers_from_attachment_alone_with_no_chunks(monkeypatch):
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = MagicMock(text="It's a null pointer exception.")
    monkeypatch.setattr(llm, "_gemini", lambda: fake_client)

    attachments = [{"filename": "log.txt", "mime_type": "text/plain", "data": base64.b64encode(b"NPE at line 1").decode()}]
    result = llm.ask_codebase("what does this log say?", [], attachments=attachments)

    assert result["answer"] == "It's a null pointer exception."
    fake_client.models.generate_content.assert_called_once()


def test_ask_codebase_falls_back_gracefully_on_gemini_error(monkeypatch):
    chunk = MagicMock(file_path="auth.py", start_line=1, end_line=10, symbol_name="login", chunk_type="function", content="...")

    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = RuntimeError("gemini is down")
    monkeypatch.setattr(llm, "_gemini", lambda: fake_client)

    result = llm.ask_codebase("where is auth handled?", [chunk])

    assert "temporarily unavailable" in result["answer"].lower()


def test_raw_completion_returns_response_text(monkeypatch):
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = MagicMock(text="hello world")
    monkeypatch.setattr(llm, "_gemini", lambda: fake_client)

    assert llm.raw_completion("prompt") == "hello world"
