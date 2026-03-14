import json
import subprocess
import sys
from pathlib import Path

import pytest

import codeindex.config as config_module


def run_cmd(cmd, cwd, check=True):
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=check)


def test_init_sync_query_status(tmp_path: Path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "app.py").write_text("def auth_user(x):\n    return x\n", encoding="utf-8")

    config = tmp_path / "codeindex.yaml"
    repo_root = Path(__file__).resolve().parents[1]
    run_cmd(
        [
            sys.executable,
            "-m",
            "codeindex.cli",
            "--config",
            str(config),
            "init",
            "--path",
            str(project),
            "--workspace",
            "myapp",
        ],
        cwd=repo_root,
    )

    assert "workspace:" in config.read_text(encoding="utf-8")

    sync = run_cmd([sys.executable, "-m", "codeindex.cli", "--config", str(config), "sync"], cwd=repo_root)
    sync_payload = json.loads(sync.stdout)
    assert sync_payload["indexed"] >= 1

    query = run_cmd(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "query", "auth logic", "--workspace", "myapp"],
        cwd=repo_root,
    )
    query_payload = json.loads(query.stdout)
    assert query_payload["results"]
    assert query_payload["metrics"]["mode"] == "hybrid"
    assert query_payload["metrics"]["vector_backend"] in {"sqlite-vec", "sqlite-vss", "python-cosine"}
    assert "estimated_tokens_saved" in query_payload["metrics"]

    status = run_cmd([sys.executable, "-m", "codeindex.cli", "--config", str(config), "status"], cwd=repo_root)
    status_payload = json.loads(status.stdout)
    assert status_payload["files"] >= 1
    assert status_payload["symbols"] >= 1


def test_global_docs_included_by_default(tmp_path: Path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "main.py").write_text("def noop():\n    return None\n", encoding="utf-8")

    global_docs = tmp_path / "global"
    global_docs.mkdir()
    (global_docs / "notes.md").write_text("authentication middleware and login flow", encoding="utf-8")

    config = tmp_path / "codeindex.yaml"
    repo_root = Path(__file__).resolve().parents[1]

    run_cmd(
        [
            sys.executable,
            "-m",
            "codeindex.cli",
            "--config",
            str(config),
            "init",
            "--path",
            str(project),
            "--workspace",
            "myapp",
            "--global-docs",
            str(global_docs),
        ],
        cwd=repo_root,
    )

    run_cmd([sys.executable, "-m", "codeindex.cli", "--config", str(config), "sync"], cwd=repo_root)
    query = run_cmd(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "query", "authentication middleware", "--workspace", "myapp"],
        cwd=repo_root,
    )
    payload = json.loads(query.stdout)
    assert any(r["workspace"] == "global" for r in payload["results"])


def test_symbol_mode_prefers_indexed_symbols(tmp_path: Path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "service.py").write_text(
        "class AuthService:\n"
        "    def login_user(self, token):\n"
        "        return token\n\n"
        "def unrelated():\n"
        "    return 1\n",
        encoding="utf-8",
    )

    config = tmp_path / "codeindex.yaml"
    repo_root = Path(__file__).resolve().parents[1]
    run_cmd(
        [
            sys.executable,
            "-m",
            "codeindex.cli",
            "--config",
            str(config),
            "init",
            "--path",
            str(project),
            "--workspace",
            "svc",
        ],
        cwd=repo_root,
    )
    run_cmd([sys.executable, "-m", "codeindex.cli", "--config", str(config), "sync"], cwd=repo_root)

    query = run_cmd(
        [
            sys.executable,
            "-m",
            "codeindex.cli",
            "--config",
            str(config),
            "query",
            "login_user symbol",
            "--workspace",
            "svc",
            "--mode",
            "symbols",
            "--top-k",
            "1",
        ],
        cwd=repo_root,
    )
    payload = json.loads(query.stdout)
    assert payload["results"][0]["kind"] == "symbol"
    assert payload["results"][0]["symbol"] == "function:login_user"


def test_invalid_persisted_mode_fails_fast(tmp_path: Path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "app.py").write_text("def auth_user(x):\n    return x\n", encoding="utf-8")

    config = tmp_path / "codeindex.yaml"
    repo_root = Path(__file__).resolve().parents[1]
    run_cmd(
        [
            sys.executable,
            "-m",
            "codeindex.cli",
            "--config",
            str(config),
            "init",
            "--path",
            str(project),
            "--workspace",
            "myapp",
        ],
        cwd=repo_root,
    )
    run_cmd([sys.executable, "-m", "codeindex.cli", "--config", str(config), "sync"], cwd=repo_root)

    config.write_text(config.read_text(encoding="utf-8").replace("mode: hybrid", "mode: invalid"), encoding="utf-8")
    query = run_cmd(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "query", "auth", "--workspace", "myapp"],
        cwd=repo_root,
        check=False,
    )
    assert query.returncode == 1
    assert "query.mode" in query.stdout


def test_malformed_config_structure_is_rejected(tmp_path: Path):
    config = tmp_path / "codeindex.yaml"
    config.write_text("workspace: demo\npaths: []\n", encoding="utf-8")

    result = run_cmd(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "status"],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
    )
    assert result.returncode == 1
    assert "paths" in result.stdout


def test_load_config_requires_pyyaml_when_config_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config = tmp_path / "codeindex.yaml"
    config.write_text("workspace: demo\n", encoding="utf-8")

    monkeypatch.setattr(config_module, "yaml", None)
    monkeypatch.setattr(config_module, "YAML_IMPORT_ERROR", ImportError("missing"))

    with pytest.raises(RuntimeError, match="PyYAML is required"):
        config_module.load_config(config)


def test_binaryish_files_do_not_break_sync(tmp_path: Path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "app.py").write_text("def auth_user(x):\n    return x\n", encoding="utf-8")
    (project / "broken.py").write_bytes(b"\x00\x01\x02\x03")

    config = tmp_path / "codeindex.yaml"
    repo_root = Path(__file__).resolve().parents[1]
    run_cmd(
        [
            sys.executable,
            "-m",
            "codeindex.cli",
            "--config",
            str(config),
            "init",
            "--path",
            str(project),
            "--workspace",
            "myapp",
        ],
        cwd=repo_root,
    )

    sync = run_cmd([sys.executable, "-m", "codeindex.cli", "--config", str(config), "sync"], cwd=repo_root)
    sync_payload = json.loads(sync.stdout)
    assert sync_payload["indexed"] == 1

    status = run_cmd([sys.executable, "-m", "codeindex.cli", "--config", str(config), "status"], cwd=repo_root)
    status_payload = json.loads(status.stdout)
    assert status_payload["files"] == 1


def test_sync_removes_deleted_files_from_index(tmp_path: Path):
    project = tmp_path / "proj"
    project.mkdir()
    target = project / "app.py"
    target.write_text("def auth_user(x):\n    return x\n", encoding="utf-8")

    config = tmp_path / "codeindex.yaml"
    repo_root = Path(__file__).resolve().parents[1]
    run_cmd(
        [
            sys.executable,
            "-m",
            "codeindex.cli",
            "--config",
            str(config),
            "init",
            "--path",
            str(project),
            "--workspace",
            "myapp",
        ],
        cwd=repo_root,
    )
    run_cmd([sys.executable, "-m", "codeindex.cli", "--config", str(config), "sync"], cwd=repo_root)

    target.unlink()
    sync = run_cmd([sys.executable, "-m", "codeindex.cli", "--config", str(config), "sync"], cwd=repo_root)
    sync_payload = json.loads(sync.stdout)
    assert sync_payload["deleted"] == 1

    status = run_cmd([sys.executable, "-m", "codeindex.cli", "--config", str(config), "status"], cwd=repo_root)
    status_payload = json.loads(status.stdout)
    assert status_payload["files"] == 0


def test_analyze_commands_cover_ast_dependencies_usage_and_stats(tmp_path: Path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "service.py").write_text(
        "import json\n"
        "from pathlib import Path\n\n"
        "def login_user(token):\n"
        "    if token:\n"
        "        return token\n"
        "    return None\n",
        encoding="utf-8",
    )
    (project / "api.py").write_text(
        "from service import login_user\n\n"
        "def run(token):\n"
        "    return login_user(token)\n",
        encoding="utf-8",
    )

    config = tmp_path / "codeindex.yaml"
    repo_root = Path(__file__).resolve().parents[1]
    run_cmd(
        [
            sys.executable,
            "-m",
            "codeindex.cli",
            "--config",
            str(config),
            "init",
            "--path",
            str(project),
            "--workspace",
            "svc",
        ],
        cwd=repo_root,
    )

    ast_query = run_cmd(
        [
            sys.executable,
            "-m",
            "codeindex.cli",
            "--config",
            str(config),
            "analyze",
            "ast",
            "--path",
            "service.py",
            "--node-type",
            "FunctionDef",
            "--name-contains",
            "login",
        ],
        cwd=repo_root,
    )
    ast_payload = json.loads(ast_query.stdout)
    assert ast_payload["count"] >= 1
    assert ast_payload["nodes"][0]["name"] == "login_user"

    deps_query = run_cmd(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "analyze", "dependencies", "--path", "service.py"],
        cwd=repo_root,
    )
    deps_payload = json.loads(deps_query.stdout)
    assert "json" in deps_payload["dependencies"]

    usage_query = run_cmd(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "analyze", "usage", "--symbol", "login_user"],
        cwd=repo_root,
    )
    usage_payload = json.loads(usage_query.stdout)
    assert usage_payload["count"] >= 2

    stats_query = run_cmd([sys.executable, "-m", "codeindex.cli", "--config", str(config), "analyze", "stats"], cwd=repo_root)
    stats_payload = json.loads(stats_query.stdout)
    assert stats_payload["files"] == 2


def test_memory_cli_commands_capture_and_search(tmp_path: Path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "auth.py").write_text("def authenticate(token):\n    return token\n", encoding="utf-8")

    config = tmp_path / "codeindex.yaml"
    repo_root = Path(__file__).resolve().parents[1]
    run_cmd(
        [
            sys.executable,
            "-m",
            "codeindex.cli",
            "--config",
            str(config),
            "init",
            "--path",
            str(project),
            "--workspace",
            "memapp",
        ],
        cwd=repo_root,
    )
    run_cmd([sys.executable, "-m", "codeindex.cli", "--config", str(config), "sync"], cwd=repo_root)
    run_cmd(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "query", "authenticate", "--workspace", "memapp"],
        cwd=repo_root,
    )

    status = run_cmd([sys.executable, "-m", "codeindex.cli", "--config", str(config), "memory", "status"], cwd=repo_root)
    status_payload = json.loads(status.stdout)
    assert status_payload["sessions"] >= 1
    assert status_payload["observations"] >= 1

    search = run_cmd(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "memory", "search", "authenticate", "--workspace", "memapp"],
        cwd=repo_root,
    )
    search_payload = json.loads(search.stdout)
    assert search_payload["results"]
    assert "estimated_tokens_summary" in search_payload
    observation_id = search_payload["results"][0]["observation_id"]

    expand = run_cmd(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "memory", "expand", observation_id],
        cwd=repo_root,
    )
    expand_payload = json.loads(expand.stdout)
    assert expand_payload["observation_id"] == observation_id

    citations = run_cmd(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "memory", "citations", observation_id],
        cwd=repo_root,
    )
    citations_payload = json.loads(citations.stdout)
    assert citations_payload["citations"]
