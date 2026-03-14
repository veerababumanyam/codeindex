import json
import subprocess
import sys
from pathlib import Path


def run_cmd(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=True)


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

    status = run_cmd([sys.executable, "-m", "codeindex.cli", "--config", str(config), "status"], cwd=repo_root)
    status_payload = json.loads(status.stdout)
    assert status_payload["files"] >= 1


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
