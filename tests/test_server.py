import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def run_cmd(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=True)


def test_search_endpoint_returns_results(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    project = tmp_path / "proj"
    project.mkdir()
    (project / "auth.py").write_text("def authenticate(token):\n    return token\n", encoding="utf-8")

    config = tmp_path / "codeindex.yaml"
    run_cmd(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "init", "--path", str(project), "--workspace", "api"],
        cwd=repo_root,
    )
    run_cmd([sys.executable, "-m", "codeindex.cli", "--config", str(config), "sync"], cwd=repo_root)

    port = 9134
    proc = subprocess.Popen(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "serve", "--host", "127.0.0.1", "--port", str(port)],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        time.sleep(0.8)
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/search?query=authenticate&workspace=api&top_k=1"
        ) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        assert payload["results"]
        assert payload["results"][0]["path"] == "auth.py"
    finally:
        proc.terminate()
        proc.wait(timeout=5)
