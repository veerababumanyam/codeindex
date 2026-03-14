from concurrent.futures import ThreadPoolExecutor
import json
import os
import subprocess
import sys
import time
import urllib.request
from urllib.error import HTTPError, URLError
from pathlib import Path

from codeindex.memory_viewer import render_viewer_page


def run_cmd(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=True)


def merged_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    if extra:
        env.update(extra)
    return env


def fetch_json(url: str, headers: dict[str, str] | None = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def post_json(url: str, payload: dict, headers: dict[str, str] | None = None) -> dict:
    all_headers = {"Content-Type": "application/json"}
    if headers:
        all_headers.update(headers)
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=all_headers,
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def append_server_config(config: Path, lines: list[str]) -> None:
    original = config.read_text(encoding="utf-8")
    config.write_text(original + "\nserver:\n" + "\n".join(f"  {line}" for line in lines) + "\n", encoding="utf-8")


def wait_for_server(proc: subprocess.Popen[str], url: str, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            stdout, stderr = proc.communicate(timeout=5)
            raise AssertionError(f"server exited early\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}")
        try:
            with urllib.request.urlopen(url):
                return
        except HTTPError:
            return
        except (URLError, ConnectionResetError):
            time.sleep(0.1)
    raise AssertionError(f"server did not become ready within {timeout} seconds for {url}")


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
        wait_for_server(proc, f"http://127.0.0.1:{port}/search?query=authenticate&workspace=api&top_k=1&mode=hybrid")
        payload = fetch_json(f"http://127.0.0.1:{port}/search?query=authenticate&workspace=api&top_k=1&mode=hybrid")
        assert payload["results"]
        assert payload["results"][0]["path"] == "auth.py"
        assert payload["metrics"]["mode"] == "hybrid"
        assert payload["metrics"]["vector_backend"] in {"sqlite-vec", "sqlite-vss", "python-cosine"}
        assert isinstance(payload["metrics"]["vector_accelerated"], bool)
        assert "estimated_tokens_saved" in payload["metrics"]
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_remote_bind_requires_explicit_opt_in(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    project = tmp_path / "proj"
    project.mkdir()
    (project / "auth.py").write_text("def authenticate(token):\n    return token\n", encoding="utf-8")

    config = tmp_path / "codeindex.yaml"
    run_cmd(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "init", "--path", str(project), "--workspace", "api"],
        cwd=repo_root,
    )

    result = subprocess.run(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "serve", "--host", "0.0.0.0", "--port", "9133"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Refusing to bind to non-loopback host '0.0.0.0'" in result.stdout


def test_remote_bind_succeeds_with_explicit_opt_in(tmp_path: Path):
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

    port = 9139
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "codeindex.cli",
            "--config",
            str(config),
            "serve",
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
            "--allow-remote",
        ],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_for_server(proc, f"http://127.0.0.1:{port}/search?query=authenticate&workspace=api")
        payload = fetch_json(f"http://127.0.0.1:{port}/search?query=authenticate&workspace=api")
        assert payload["results"]
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
        wait_for_server(proc, f"http://127.0.0.1:{port}/search?query=authenticate&workspace=api&top_k=1&mode=hybrid")
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
        wait_for_server(proc, f"http://127.0.0.1:{port}/analysis/stats")
        usage = fetch_json(f"http://127.0.0.1:{port}/analysis/usage?symbol=login_user")
        assert usage["count"] >= 2

        deps = fetch_json(f"http://127.0.0.1:{port}/analysis/dependencies?path=service.py")
        assert "json" in deps["dependencies"]

        stats = fetch_json(f"http://127.0.0.1:{port}/analysis/stats")
        assert stats["files"] == 2
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_analysis_endpoint_rejects_root_override_and_escape_paths(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    project = tmp_path / "proj"
    project.mkdir()
    (project / "service.py").write_text("def login_user(token):\n    return token\n", encoding="utf-8")
    outside = tmp_path / "outside.py"
    outside.write_text("secret = True\n", encoding="utf-8")

    config = tmp_path / "codeindex.yaml"
    run_cmd(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "init", "--path", str(project), "--workspace", "api"],
        cwd=repo_root,
    )
    run_cmd([sys.executable, "-m", "codeindex.cli", "--config", str(config), "sync"], cwd=repo_root)

    port = 9142
    proc = subprocess.Popen(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "serve", "--host", "127.0.0.1", "--port", str(port)],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_for_server(proc, f"http://127.0.0.1:{port}/analysis/stats")
        with HTTPErrorContext(400):
            fetch_json(
                f"http://127.0.0.1:{port}/analysis/validate?path=service.py&root="
                f"{urllib.request.pathname2url(str(tmp_path.resolve()))}"
            )
        with HTTPErrorContext(400):
            fetch_json(f"http://127.0.0.1:{port}/analysis/validate?path=../outside.py")
        with HTTPErrorContext(400):
            fetch_json(f"http://127.0.0.1:{port}/analysis/validate?path={urllib.request.pathname2url(str(outside.resolve()))}")
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_analysis_endpoints_reject_root_override_and_escape_attempts(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    project = tmp_path / "proj"
    project.mkdir()
    (project / "service.py").write_text("def login_user(token):\n    return token\n", encoding="utf-8")
    outside = tmp_path / "outside.py"
    outside.write_text("def secret():\n    return 'nope'\n", encoding="utf-8")

    config = tmp_path / "codeindex.yaml"
    run_cmd(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "init", "--path", str(project), "--workspace", "api"],
        cwd=repo_root,
    )
    run_cmd([sys.executable, "-m", "codeindex.cli", "--config", str(config), "sync"], cwd=repo_root)

    port = 9142
    proc = subprocess.Popen(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "serve", "--host", "127.0.0.1", "--port", str(port)],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_for_server(proc, f"http://127.0.0.1:{port}/search?query=authenticate&workspace=api")
        with HTTPErrorContext(400):
            fetch_json(
                f"http://127.0.0.1:{port}/analysis/symbols?root={urllib.request.pathname2url(str(tmp_path))}&path=service.py"
            )
        with HTTPErrorContext(400):
            fetch_json(f"http://127.0.0.1:{port}/analysis/symbols?path=..%2Foutside.py")
        with HTTPErrorContext(400):
            fetch_json(
                f"http://127.0.0.1:{port}/analysis/symbols?path={urllib.request.pathname2url(str(outside))}"
            )

        mcp_payload = post_json(
            f"http://127.0.0.1:{port}/mcp",
            {
                "jsonrpc": "2.0",
                "id": 9,
                "method": "tools/call",
                "params": {
                    "name": "codeindex_analyze",
                    "arguments": {"kind": "symbols", "root": str(tmp_path), "path": "service.py"},
                },
            },
        )
        assert mcp_payload["error"]["code"] == -32602
        assert "root overrides are not allowed" in mcp_payload["error"]["message"]
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_auth_token_protects_http_endpoints(tmp_path: Path):
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
    append_server_config(config, ["auth_token: secret-token", "auth_token_header: X-CodeIndex-Token"])

    port = 9140
    proc = subprocess.Popen(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "serve", "--host", "127.0.0.1", "--port", str(port)],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_for_server(proc, f"http://127.0.0.1:{port}/mcp")
        with HTTPErrorContext(401):
            fetch_json(f"http://127.0.0.1:{port}/search?query=authenticate&workspace=api")
        with HTTPErrorContext(401):
            fetch_json(f"http://127.0.0.1:{port}/memory/status?workspace=api")

        payload = fetch_json(
            f"http://127.0.0.1:{port}/search?query=authenticate&workspace=api",
            headers={"X-CodeIndex-Token": "secret-token"},
        )
        assert payload["results"]
    finally:
        proc.terminate()
        proc.wait(timeout=5)


class HTTPErrorContext:
    def __init__(self, status_code: int):
        self.status_code = status_code

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            raise AssertionError(f"Expected HTTP {self.status_code}")
        if not issubclass(exc_type, HTTPError):
            return False
        assert exc.code == self.status_code
        return True


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
        wait_for_server(proc, f"http://127.0.0.1:{port}/mcp")
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


def test_auth_token_protects_mcp_endpoint(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    project = tmp_path / "proj"
    project.mkdir()
    (project / "service.py").write_text("def login_user(token):\n    return token\n", encoding="utf-8")

    config = tmp_path / "codeindex.yaml"
    run_cmd(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "init", "--path", str(project), "--workspace", "api"],
        cwd=repo_root,
    )
    run_cmd([sys.executable, "-m", "codeindex.cli", "--config", str(config), "sync"], cwd=repo_root)
    append_server_config(config, ["auth_token: mcp-secret", "auth_token_header: X-CodeIndex-Token"])

    port = 9141
    proc = subprocess.Popen(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "serve", "--host", "127.0.0.1", "--port", str(port)],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_for_server(proc, f"http://127.0.0.1:{port}/memory/viewer")
        with HTTPErrorContext(401):
            post_json(
                f"http://127.0.0.1:{port}/mcp",
                {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            )

        call = post_json(
            f"http://127.0.0.1:{port}/mcp",
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={"X-CodeIndex-Token": "mcp-secret"},
        )
        names = {tool["name"] for tool in call["result"]["tools"]}
        assert "codeindex_search" in names
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_memory_viewer_renders_untrusted_content_as_text(tmp_path: Path):
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
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "query", "<script>alert(1)</script>", "--workspace", "mem"],
        cwd=repo_root,
    )

    port = 9143
    proc = subprocess.Popen(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "serve", "--host", "127.0.0.1", "--port", str(port)],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_for_server(proc, f"http://127.0.0.1:{port}/memory/viewer")
        viewer = urllib.request.urlopen(f"http://127.0.0.1:{port}/memory/viewer").read().decode("utf-8")
        assert "textContent = value || ''" in viewer
        assert "el.innerHTML =" not in viewer
        assert "renderCard(eventsEl, item)" in viewer
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
        wait_for_server(proc, f"http://127.0.0.1:{port}/memory/status?workspace=mem")
        status = fetch_json(f"http://127.0.0.1:{port}/memory/status?workspace=mem")
        assert status["observations"] >= 1
        assert "memory_search_backend" in status["capabilities"]

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

        mcp_status = post_json(
            f"http://127.0.0.1:{port}/mcp",
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "codeindex_memory_status",
                    "arguments": {"workspace": "mem"},
                },
            },
        )
        status_payload = json.loads(mcp_status["result"]["content"][0]["text"])
        assert status_payload["capabilities"]["memory_search_backend"] == status["capabilities"]["memory_search_backend"]
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_search_endpoint_reports_python_cosine_when_vectors_disabled(tmp_path: Path):
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

    port = 9144
    proc = subprocess.Popen(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "serve", "--host", "127.0.0.1", "--port", str(port)],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=merged_env({"CODEINDEX_DISABLE_VECTORS": "1"}),
    )
    try:
        wait_for_server(proc, f"http://127.0.0.1:{port}/search?query=authenticate&workspace=api")
        payload = fetch_json(f"http://127.0.0.1:{port}/search?query=authenticate&workspace=api")
        assert payload["results"]
        assert payload["metrics"]["vector_backend"] == "python-cosine"
        assert payload["metrics"]["vector_accelerated"] is False
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_memory_status_and_search_degrade_without_fts5(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    project = tmp_path / "proj"
    project.mkdir()
    (project / "auth.py").write_text("def authenticate(token):\n    return token\n", encoding="utf-8")

    config = tmp_path / "codeindex.yaml"
    env = {"CODEINDEX_DISABLE_FTS5": "1"}
    run_cmd(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "init", "--path", str(project), "--workspace", "mem"],
        cwd=repo_root,
    )
    subprocess.run(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "sync"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=True,
        env=merged_env(env),
    )
    subprocess.run(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "query", "authenticate", "--workspace", "mem"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=True,
        env=merged_env(env),
    )

    port = 9145
    proc = subprocess.Popen(
        [sys.executable, "-m", "codeindex.cli", "--config", str(config), "serve", "--host", "127.0.0.1", "--port", str(port)],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=merged_env(env),
    )
    try:
        wait_for_server(proc, f"http://127.0.0.1:{port}/memory/status?workspace=mem")
        status = fetch_json(f"http://127.0.0.1:{port}/memory/status?workspace=mem")
        assert status["capabilities"]["memory_search_backend"] == "sql-like"
        assert status["capabilities"]["fts5_available"] is False
        assert status["capabilities"]["degraded"] is True

        search = fetch_json(f"http://127.0.0.1:{port}/memory/search?workspace=mem&query=authenticate")
        assert search["results"]

        mcp_status = post_json(
            f"http://127.0.0.1:{port}/mcp",
            {
                "jsonrpc": "2.0",
                "id": 11,
                "method": "tools/call",
                "params": {
                    "name": "codeindex_memory_status",
                    "arguments": {"workspace": "mem"},
                },
            },
        )
        parsed_status = json.loads(mcp_status["result"]["content"][0]["text"])
        assert parsed_status["capabilities"]["memory_search_backend"] == "sql-like"
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_memory_viewer_renders_untrusted_content_with_text_nodes():
    page = render_viewer_page('<img src=x onerror="alert(1)">').decode("utf-8")

    assert "textContent" in page
    assert "el.innerHTML =" not in page
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in page
