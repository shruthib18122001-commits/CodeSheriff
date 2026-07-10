import textwrap
from unittest.mock import MagicMock

from app.services import ingestion

PYTHON_SAMPLE = textwrap.dedent(
    """
    import os


    def greet(name):
        return f"Hello, {name}!"


    class Greeter:
        def __init__(self, name):
            self.name = name

        def greet(self):
            return greet(self.name)
    """
)

TS_SAMPLE = textwrap.dedent(
    """
    export function add(a: number, b: number): number {
      return a + b;
    }

    export class Calculator {
      total = 0;

      add(value: number): void {
        this.total += value;
      }
    }
    """
)


def test_chunk_python_file_extracts_function_and_class(tmp_path):
    path = tmp_path / "sample.py"
    path.write_text(PYTHON_SAMPLE)

    chunks = ingestion._chunk_file(path, tmp_path)
    pairs = {(c["chunk_type"], c["symbol_name"]) for c in chunks}

    assert ("function", "greet") in pairs
    assert ("class", "Greeter") in pairs
    # methods inside a class should also surface as their own chunks
    assert any(c["chunk_type"] == "function" and c["symbol_name"] == "__init__" for c in chunks)
    for c in chunks:
        assert c["file_path"] == "sample.py"
        assert c["start_line"] <= c["end_line"]


def test_chunk_typescript_file_extracts_function_and_class(tmp_path):
    path = tmp_path / "sample.ts"
    path.write_text(TS_SAMPLE)

    chunks = ingestion._chunk_file(path, tmp_path)
    pairs = {(c["chunk_type"], c["symbol_name"]) for c in chunks}

    assert ("function", "add") in pairs
    assert ("class", "Calculator") in pairs


def test_chunk_file_falls_back_to_module_chunk_when_no_functions_or_classes(tmp_path):
    path = tmp_path / "constants.py"
    path.write_text("MAX_RETRIES = 3\nTIMEOUT = 30\n")

    chunks = ingestion._chunk_file(path, tmp_path)

    assert len(chunks) == 1
    assert chunks[0]["chunk_type"] == "module"


def test_looks_binary_detects_null_bytes(tmp_path):
    binary_path = tmp_path / "image.bin"
    binary_path.write_bytes(b"\x00\x01\x02binarydata")

    assert ingestion._looks_binary(binary_path) is True


def test_looks_binary_is_false_for_text_file(tmp_path):
    text_path = tmp_path / "notes.txt"
    text_path.write_text("just some plain text")

    assert ingestion._looks_binary(text_path) is False


def test_parse_repository_skips_oversized_files(tmp_path):
    (tmp_path / "small.py").write_text("def ok():\n    return 1\n")

    big_content = "def big_function():\n    x = 1\n" + ("# padding\n" * 200_000)
    (tmp_path / "big.py").write_text(big_content)

    chunks = ingestion._parse_repository(str(tmp_path))
    files_seen = {c["file_path"] for c in chunks}

    assert "small.py" in files_seen
    assert "big.py" not in files_seen


def test_parse_repository_skips_lock_files_and_skip_dirs(tmp_path):
    (tmp_path / "package-lock.json").write_text("{}")
    node_modules = tmp_path / "node_modules"
    node_modules.mkdir()
    (node_modules / "dep.js").write_text("function dep() { return 1; }")
    (tmp_path / "app.js").write_text("function real() { return 2; }")

    chunks = ingestion._parse_repository(str(tmp_path))
    files_seen = {c["file_path"] for c in chunks}

    assert "app.js" in files_seen
    assert "package-lock.json" not in files_seen
    assert not any("node_modules" in f for f in files_seen)


def test_parse_repository_includes_readme_as_special_chunk(tmp_path):
    (tmp_path / "README.md").write_text("# My Project\nThis does things.")
    (tmp_path / "app.py").write_text("def main():\n    pass\n")

    chunks = ingestion._parse_repository(str(tmp_path))
    readme_chunks = [c for c in chunks if c["chunk_type"] == "readme"]

    assert len(readme_chunks) == 1
    assert readme_chunks[0]["file_path"] == "README.md"


def test_parse_repository_skips_unparseable_file_without_aborting(tmp_path, monkeypatch):
    (tmp_path / "good.py").write_text("def fine():\n    return 1\n")
    (tmp_path / "bad.py").write_text("def also_fine():\n    return 2\n")

    real_chunk_file = ingestion._chunk_file

    def flaky_chunk_file(path, root):
        if path.name == "bad.py":
            raise RuntimeError("simulated parser crash")
        return real_chunk_file(path, root)

    monkeypatch.setattr(ingestion, "_chunk_file", flaky_chunk_file)

    chunks = ingestion._parse_repository(str(tmp_path))
    files_seen = {c["file_path"] for c in chunks}

    assert "good.py" in files_seen
    assert "bad.py" not in files_seen


def test_run_ingestion_pipeline_marks_failed_instead_of_raising(monkeypatch):
    fake_repo_row = MagicMock()
    fake_repo_row.id = "repo-1"

    fake_db = MagicMock()
    fake_db.query.return_value.filter.return_value.first.return_value = fake_repo_row

    monkeypatch.setattr(ingestion, "SessionLocal", lambda: fake_db)

    def boom(*args, **kwargs):
        raise RuntimeError("clone failed")

    monkeypatch.setattr(ingestion, "_clone_repo", boom)

    # Must not raise -- an unhandled exception here would crash the RQ worker.
    ingestion.run_ingestion_pipeline("repo-1")

    assert fake_repo_row.index_status == ingestion.IndexStatus.failed
