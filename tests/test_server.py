from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def run_cmd(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=True)


def fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode("utf-8"))


def post_json(url: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


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
        payload = fetch_json(f"http://127.0.0.1:{port}/search?query=authenticate&workspace=api&top_k=1&mode=hybrid")
        assert payload["results"]
        assert payload["results"][0]["path"] == "auth.py"
        assert payload["metrics"]["mode"] == "hybrid"
        assert payload["metrics"]["vector_backend"] in {"sqlite-vec", "sqlite-vss", "python-cosine"}
        assert "estimated_tokens_saved" in payload["metrics"]
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_search_endpoint_handles_concurrent_requests(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    project = tmp_path / "proj"
    project.mkdir()
    (project / "auth.py").write_text("def authenticate(token):\n    return token\n", encoding="utf-8")
    (project / "session.py").write_text("def authorize_session(token):\n    return token\n", encoding="utf-8")

    config = tmp_path / "codeindex.yaml"
    run_cmd(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "init", "--path", str(project), "--workspace", "api"],
        cwd=repo_root,
    )
    run_cmd([sys.executable, "-m", "codeindex.cli", "--config", str(config), "sync"], cwd=repo_root)

    port = 9135
    proc = subprocess.Popen(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "serve", "--host", "127.0.0.1", "--port", str(port)],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        time.sleep(0.8)
        url = f"http://127.0.0.1:{port}/search?query=authenticate&workspace=api&top_k=1&mode=hybrid"
        with ThreadPoolExecutor(max_workers=8) as pool:
            payloads = list(pool.map(fetch_json, [url] * 12))
        assert all(payload["results"] for payload in payloads)
        assert all(payload["results"][0]["path"] in {"auth.py", "session.py"} for payload in payloads)
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_analysis_endpoints_return_project_insights(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    project = tmp_path / "proj"
    project.mkdir()
    (project / "service.py").write_text(
        "import json\n\n"
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
    run_cmd(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "init", "--path", str(project), "--workspace", "api"],
        cwd=repo_root,
    )
    run_cmd([sys.executable, "-m", "codeindex.cli", "--config", str(config), "sync"], cwd=repo_root)

    port = 9136
    proc = subprocess.Popen(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "serve", "--host", "127.0.0.1", "--port", str(port)],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        time.sleep(0.8)
        usage = fetch_json(f"http://127.0.0.1:{port}/analysis/usage?symbol=login_user")
        assert usage["count"] >= 2

        deps = fetch_json(f"http://127.0.0.1:{port}/analysis/dependencies?path=service.py")
        assert "json" in deps["dependencies"]

        stats = fetch_json(f"http://127.0.0.1:{port}/analysis/stats")
        assert stats["files"] == 2
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_mcp_jsonrpc_tools_list_and_call(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    project = tmp_path / "proj"
    project.mkdir()
    (project / "service.py").write_text(
        "def login_user(token):\n"
        "    return token\n",
        encoding="utf-8",
    )

    config = tmp_path / "codeindex.yaml"
    run_cmd(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "init", "--path", str(project), "--workspace", "api"],
        cwd=repo_root,
    )
    run_cmd([sys.executable, "-m", "codeindex.cli", "--config", str(config), "sync"], cwd=repo_root)

    port = 9137
    proc = subprocess.Popen(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "serve", "--host", "127.0.0.1", "--port", str(port)],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        time.sleep(0.8)
        base = f"http://127.0.0.1:{port}/mcp"
        tools = post_json(base, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = {tool["name"] for tool in tools["result"]["tools"]}
        assert "codeindex_search" in names
        assert "codeindex_analyze" in names
        assert "codeindex_memory_search" in names
        assert "codeindex_memory_status" in names

        call = post_json(
            base,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "codeindex_analyze", "arguments": {"kind": "usage", "symbol": "login_user"}},
            },
        )
        text_payload = call["result"]["content"][0]["text"]
        parsed_payload = json.loads(text_payload)
        assert parsed_payload["count"] >= 1
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_memory_http_endpoints_and_mcp_tools(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    project = tmp_path / "proj"
    project.mkdir()
    (project / "auth.py").write_text("def authenticate(token):\n    return token\n", encoding="utf-8")

    config = tmp_path / "codeindex.yaml"
    run_cmd(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "init", "--path", str(project), "--workspace", "mem"],
        cwd=repo_root,
    )
    run_cmd([sys.executable, "-m", "codeindex.cli", "--config", str(config), "sync"], cwd=repo_root)
    run_cmd(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "query", "authenticate", "--workspace", "mem"],
        cwd=repo_root,
    )

    port = 9138
    proc = subprocess.Popen(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "serve", "--host", "127.0.0.1", "--port", str(port)],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        time.sleep(0.8)
        status = fetch_json(f"http://127.0.0.1:{port}/memory/status?workspace=mem")
        assert status["observations"] >= 1

        search = fetch_json(f"http://127.0.0.1:{port}/memory/search?workspace=mem&query=authenticate")
        assert search["results"]
        observation_id = search["results"][0]["observation_id"]

        expand = fetch_json(f"http://127.0.0.1:{port}/memory/observations/{observation_id}")
        assert expand["observation_id"] == observation_id

        sessions = fetch_json(f"http://127.0.0.1:{port}/memory/sessions?workspace=mem")
        assert sessions["sessions"]

        viewer = urllib.request.urlopen(f"http://127.0.0.1:{port}/memory/viewer").read().decode("utf-8")
        assert "Persistent Memory Viewer" in viewer

        stream = urllib.request.urlopen(f"http://127.0.0.1:{port}/memory/stream?workspace=mem").read().decode("utf-8")
        assert "data:" in stream

        mcp_search = post_json(
            f"http://127.0.0.1:{port}/mcp",
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "codeindex_memory_search",
                    "arguments": {"workspace": "mem", "query": "authenticate"},
                },
            },
        )
        parsed = json.loads(mcp_search["result"]["content"][0]["text"])
        assert parsed["results"]
    finally:
        proc.terminate()
        proc.wait(timeout=5)
