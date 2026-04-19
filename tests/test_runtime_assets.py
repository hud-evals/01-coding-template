"""Unit tests for :mod:`ast_pilot.runtime_assets`."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ast_pilot.runtime_assets import (  # noqa: E402
    SIZE_REFUSE_BYTES,
    collect_runtime_assets,
    extract_references,
)


def _write_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    """Write a fake repo tree under *tmp_path* and return its root."""

    for rel, content in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return tmp_path


def _assets_keyed(result) -> dict[str, str]:
    """Convenience view: rel_path -> kind."""

    return {rel: asset.kind for rel, asset in result.items()}


# ---------------------------------------------------------------------------
# Literal ``open`` with plain string paths
# ---------------------------------------------------------------------------


def test_open_literal_relative_to_source(tmp_path):
    repo = _write_repo(
        tmp_path,
        {
            "schema.sql": "CREATE TABLE t (id INTEGER);\n",
            "src/app.py": "with open('schema.sql') as f: schema = f.read()\n",
        },
    )
    result = collect_runtime_assets([repo / "src" / "app.py"], repo)
    assert _assets_keyed(result) == {"schema.sql": "bundled"}


def test_open_literal_relative_to_repo_root(tmp_path):
    repo = _write_repo(
        tmp_path,
        {
            "schema.sql": "CREATE TABLE t (id INTEGER);",
            "src/app.py": "",
            "src/tests/test_app.py": (
                "with open('schema.sql') as f:\n"
                "    pass\n"
            ),
        },
    )
    result = collect_runtime_assets(
        [repo / "src" / "tests" / "test_app.py"],
        repo,
        import_roots=[repo / "src"],
    )
    assert "schema.sql" in result
    assert result["schema.sql"].kind == "bundled"


def test_open_joined_with_repo_root_constant(tmp_path):
    repo = _write_repo(
        tmp_path,
        {
            "schema.sql": "CREATE TABLE t (id);",
            "test_app.py": (
                "import os\n"
                "REPO_ROOT = os.path.dirname(os.path.abspath(__file__))\n"
                "with open(os.path.join(REPO_ROOT, 'schema.sql')) as f:\n"
                "    pass\n"
            ),
        },
    )
    result = collect_runtime_assets([repo / "test_app.py"], repo)
    assert "schema.sql" in result
    assert result["schema.sql"].kind == "bundled"


def test_open_joined_nested_directory(tmp_path):
    repo = _write_repo(
        tmp_path,
        {
            "data/records.json": "[]",
            "test_app.py": (
                "import os\n"
                "with open(os.path.join(REPO_ROOT, 'data', 'records.json')) as f:\n"
                "    pass\n"
            ),
        },
    )
    result = collect_runtime_assets([repo / "test_app.py"], repo)
    assert "data/records.json" in result


def test_path_read_text_literal(tmp_path):
    repo = _write_repo(
        tmp_path,
        {
            "config.yaml": "key: value",
            "src/loader.py": (
                "from pathlib import Path\n"
                "Path('config.yaml').read_text()\n"
            ),
        },
    )
    result = collect_runtime_assets([repo / "src" / "loader.py"], repo)
    assert "config.yaml" in result


def test_path_dunder_file_parent_joined(tmp_path):
    repo = _write_repo(
        tmp_path,
        {
            "src/fixtures/data.json": "{}",
            "src/loader.py": (
                "from pathlib import Path\n"
                "Path(__file__).parent.joinpath('fixtures/data.json').read_text()\n"
            ),
        },
    )
    result = collect_runtime_assets([repo / "src" / "loader.py"], repo)
    assert "src/fixtures/data.json" in result


def test_path_truediv_with_dunder_file(tmp_path):
    repo = _write_repo(
        tmp_path,
        {
            "src/fixtures/data.json": "{}",
            "src/loader.py": (
                "from pathlib import Path\n"
                "(Path(__file__).parent / 'fixtures' / 'data.json').read_text()\n"
            ),
        },
    )
    result = collect_runtime_assets([repo / "src" / "loader.py"], repo)
    assert "src/fixtures/data.json" in result


# ---------------------------------------------------------------------------
# Third-party-style loaders
# ---------------------------------------------------------------------------


def test_sqlite3_connect_literal(tmp_path):
    repo = _write_repo(
        tmp_path,
        {
            "app.db": "",
            "src/app.py": (
                "import sqlite3\n"
                "conn = sqlite3.connect('app.db')\n"
            ),
        },
    )
    result = collect_runtime_assets([repo / "src" / "app.py"], repo)
    assert "app.db" in result


def test_json_load_over_open(tmp_path):
    repo = _write_repo(
        tmp_path,
        {
            "data.json": "{}",
            "src/app.py": (
                "import json\n"
                "json.load(open('data.json'))\n"
            ),
        },
    )
    result = collect_runtime_assets([repo / "src" / "app.py"], repo)
    assert "data.json" in result


def test_yaml_safe_load_open(tmp_path):
    repo = _write_repo(
        tmp_path,
        {
            "cfg.yaml": "k: v",
            "src/app.py": (
                "import yaml\n"
                "yaml.safe_load(open('cfg.yaml'))\n"
            ),
        },
    )
    result = collect_runtime_assets([repo / "src" / "app.py"], repo)
    assert "cfg.yaml" in result


# ---------------------------------------------------------------------------
# to_create_by_agent — referenced but absent
# ---------------------------------------------------------------------------


def test_unresolved_reference_is_to_create(tmp_path):
    repo = _write_repo(
        tmp_path,
        {
            "src/app.py": "",
            "tests/test_schema.py": (
                "import sqlite3\n"
                "with open('schema.sql') as f:\n"
                "    sqlite3.connect(':memory:').executescript(f.read())\n"
            ),
        },
    )
    result = collect_runtime_assets([repo / "tests" / "test_schema.py"], repo)
    assert "schema.sql" in result
    assert result["schema.sql"].kind == "to_create_by_agent"


def test_resolved_wins_over_unresolved(tmp_path):
    repo = _write_repo(
        tmp_path,
        {
            "schema.sql": "CREATE TABLE t (id);",
            "tests/a.py": "open('schema.sql')\n",
            "tests/b.py": "open('schema.sql')\n",
        },
    )
    result = collect_runtime_assets(
        [repo / "tests" / "a.py", repo / "tests" / "b.py"], repo,
    )
    assert result["schema.sql"].kind == "bundled"
    assert len(result["schema.sql"].referenced_by) == 2


# ---------------------------------------------------------------------------
# Safety: outside repo, secrets, known modules
# ---------------------------------------------------------------------------


def test_absolute_paths_outside_repo_are_skipped(tmp_path):
    repo = _write_repo(
        tmp_path,
        {
            "src/app.py": (
                "with open('/etc/passwd') as f:\n"
                "    pass\n"
            ),
        },
    )
    result = collect_runtime_assets([repo / "src" / "app.py"], repo)
    assert result == {}


def test_env_file_is_refused_by_default(tmp_path):
    repo = _write_repo(
        tmp_path,
        {
            ".env": "API_KEY=secret",
            "src/app.py": "open('.env')\n",
        },
    )
    result = collect_runtime_assets([repo / "src" / "app.py"], repo)
    assert ".env" not in result


def test_pem_file_refused_by_default(tmp_path):
    repo = _write_repo(
        tmp_path,
        {
            "private.pem": "-----BEGIN PRIVATE KEY-----",
            "src/app.py": "open('private.pem')\n",
        },
    )
    result = collect_runtime_assets([repo / "src" / "app.py"], repo)
    assert "private.pem" not in result


def test_secret_files_allowed_when_flag_set(tmp_path):
    repo = _write_repo(
        tmp_path,
        {
            ".env": "OPENAI_API_KEY=xxx",
            "src/app.py": "open('.env')\n",
        },
    )
    result = collect_runtime_assets(
        [repo / "src" / "app.py"], repo, allow_secret_patterns=True,
    )
    assert ".env" in result


def test_known_python_modules_not_bundled_as_assets(tmp_path):
    repo = _write_repo(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/util.py": "# helper",
            "src/app.py": "open('pkg/util.py')\n",
        },
    )
    result = collect_runtime_assets(
        [repo / "src" / "app.py"], repo,
        known_python_modules={"pkg", "pkg.util"},
    )
    assert "pkg/util.py" not in result


# ---------------------------------------------------------------------------
# Things we explicitly do NOT handle — document via tests
# ---------------------------------------------------------------------------


def test_variable_paths_not_reduced(tmp_path):
    repo = _write_repo(
        tmp_path,
        {
            "schema.sql": "",
            "src/app.py": (
                "path = 'schema.sql'\n"
                "open(path)\n"
            ),
        },
    )
    result = collect_runtime_assets([repo / "src" / "app.py"], repo)
    assert result == {}


def test_glob_patterns_not_bundled(tmp_path):
    repo = _write_repo(
        tmp_path,
        {
            "a.sql": "",
            "b.sql": "",
            "src/app.py": (
                "import glob\n"
                "for fn in glob.glob('*.sql'):\n"
                "    open(fn)\n"
            ),
        },
    )
    result = collect_runtime_assets([repo / "src" / "app.py"], repo)
    assert "*.sql" not in result
    assert "a.sql" not in result


def test_function_argument_paths_not_reduced(tmp_path):
    repo = _write_repo(
        tmp_path,
        {
            "src/app.py": (
                "def load(path):\n"
                "    return open(path).read()\n"
            ),
        },
    )
    result = collect_runtime_assets([repo / "src" / "app.py"], repo)
    assert result == {}


# ---------------------------------------------------------------------------
# Size guards
# ---------------------------------------------------------------------------


def test_large_file_raises_hard_limit(tmp_path, monkeypatch):
    big = tmp_path / "huge.sql"
    big.write_bytes(b"x" * 32)
    monkeypatch.setattr(
        "ast_pilot.runtime_assets.SIZE_REFUSE_BYTES", 16,
    )
    src = tmp_path / "src" / "app.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("open('huge.sql')\n", encoding="utf-8")

    with pytest.raises(ValueError, match="size limit"):
        collect_runtime_assets([src], tmp_path)


def test_large_file_warns_soft_limit(tmp_path, monkeypatch, caplog):
    asset = tmp_path / "big.json"
    asset.write_text("[]" + "x" * 200, encoding="utf-8")
    src = tmp_path / "src" / "app.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("open('big.json')\n", encoding="utf-8")

    monkeypatch.setattr("ast_pilot.runtime_assets.SIZE_WARN_BYTES", 8)
    caplog.set_level("WARNING", logger="ast_pilot.runtime_assets")

    result = collect_runtime_assets([src], tmp_path)
    assert "big.json" in result
    assert any("Bundling large" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# Multiple references and dedup
# ---------------------------------------------------------------------------


def test_same_asset_referenced_by_multiple_files(tmp_path):
    repo = _write_repo(
        tmp_path,
        {
            "data.json": "[]",
            "src/a.py": "open('data.json')\n",
            "src/b.py": "open('data.json')\n",
        },
    )
    result = collect_runtime_assets(
        [repo / "src" / "a.py", repo / "src" / "b.py"], repo,
    )
    assert "data.json" in result
    assert len(result["data.json"].referenced_by) == 2


def test_extract_references_ignores_syntax_errors(tmp_path):
    bad = tmp_path / "broken.py"
    bad.write_text("def broken(:\n    pass", encoding="utf-8")
    assert extract_references(bad) == []


def test_extract_references_handles_missing_file(tmp_path):
    missing = tmp_path / "does_not_exist.py"
    assert extract_references(missing) == []
