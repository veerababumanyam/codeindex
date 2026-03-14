from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from secrets import compare_digest
from urllib.parse import parse_qs, urlparse

from .analysis import validate_relative_path
from .config import is_loopback_host
from .analysis import (
    analyze_complexity,
    analyze_dependencies,
    extract_graph_data,
    find_symbol_usage,
    list_project_files,
    list_symbols,
    project_stats,
    query_python_ast,
    validate_syntax,
)
from .memory_service import MemoryService
from .memory_viewer import render_stream_payload, render_viewer_page
from .search import search_index
from .storage import Storage


def validate_bind_host(host: str, allow_remote: bool) -> None:
    if not allow_remote and not is_loopback_host(host):
        raise ValueError(
            f"Refusing to bind to non-loopback host '{host}' without explicit remote opt-in. "
            "Set server.allow_remote: true or pass --allow-remote."
        )


class SearchHandler(BaseHTTPRequestHandler):
    db_path: Path
    default_root: Path
    excludes: list[str]
    prefer_tree_sitter: bool
    config_data: dict[str, object]
    auth_token: str | None
    auth_token_header: str

    MCP_TOOLS = [
        {
            "name": "codeindex_search",
            "description": "Semantic search over indexed chunks and symbols",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "workspace": {"type": "string"},
                    "top_k": {"type": "integer"},
                    "include_global": {"type": "boolean"},
                    "mode": {"type": "string", "enum": ["chunks", "symbols", "hybrid"]},
                },
                "required": ["query", "workspace"],
            },
        },
        {
            "name": "codeindex_analyze",
            "description": "Run integrated Tree-sitter-aware code analysis",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["files", "symbols", "ast", "validate", "dependencies", "complexity", "usage", "stats", "graph"],
                    },
                    "root": {"type": "string"},
                    "path": {"type": "string"},
                    "symbol": {"type": "string"},
                    "node_type": {"type": "string"},
                    "name_contains": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["kind"],
            },
        },
        {
            "name": "codeindex_memory_search",
            "description": "Search persistent memory with progressive disclosure",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "workspace": {"type": "string"},
                    "layer": {"type": "string", "enum": ["summary", "expanded", "full"]},
                    "budget": {"type": "integer"},
                    "top_k": {"type": "integer"},
                },
                "required": ["query", "workspace"],
            },
        },
        {
            "name": "codeindex_memory_expand",
            "description": "Expand a memory observation by stable id",
            "inputSchema": {
                "type": "object",
                "properties": {"observation_id": {"type": "string"}},
                "required": ["observation_id"],
            },
        },
        {
            "name": "codeindex_memory_session_list",
            "description": "List memory sessions for a workspace",
            "inputSchema": {"type": "object", "properties": {"workspace": {"type": "string"}}},
        },
        {
            "name": "codeindex_memory_session_show",
            "description": "Show one memory session by id",
            "inputSchema": {
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
                "required": ["session_id"],
            },
        },
        {
            "name": "codeindex_memory_status",
            "description": "Show memory subsystem status",
            "inputSchema": {"type": "object", "properties": {"workspace": {"type": "string"}}},
        },
    ]

    def _json_response(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html_response(self, body: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _unauthorized(self) -> None:
        body = json.dumps(
            {
                "error": "Unauthorized",
                "message": f"Provide the configured API token in the {self.auth_token_header} header.",
            }
        ).encode("utf-8")
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _sse_response(self, body: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _rpc_response(self, rpc_id: object, result: dict[str, object] | None = None, error: dict[str, object] | None = None) -> None:
        payload: dict[str, object] = {"jsonrpc": "2.0", "id": rpc_id}
        if error is not None:
            payload["error"] = error
        else:
            payload["result"] = result or {}
        self._json_response(200, payload)

    def _workspace(self, params: dict[str, list[str]]) -> str:
        return params.get("workspace", [str(self.config_data.get("workspace", "default"))])[0]

    def _requires_auth(self, path: str) -> bool:
        return path == "/search" or path == "/mcp" or path.startswith("/analysis/") or path.startswith("/memory/")

    def _authorized(self) -> bool:
        if not self.auth_token:
            return True
        provided = self.headers.get(self.auth_token_header)
        return isinstance(provided, str) and compare_digest(provided, self.auth_token)

    def _trusted_analysis_root(self, params: dict[str, object]) -> Path:
        raw_root = params.get("root")
        if raw_root is not None:
            candidate = Path(str(raw_root)).resolve()
            if candidate != self.default_root:
                raise ValueError("root overrides are not allowed for server analysis")
        return self.default_root

    def _analysis_payload(self, kind: str, params: dict[str, object]) -> dict:
        root = self._trusted_analysis_root(params)
        limit = max(1, int(params.get("limit", 50)))
        rel_path = ""
        raw_path = params.get("path")
        if isinstance(raw_path, str) and raw_path.strip():
            rel_path = validate_relative_path(raw_path)
        symbol = str(params.get("symbol", "")) if params.get("symbol") is not None else ""
        node_type = str(params.get("node_type")) if params.get("node_type") is not None else None
        name_contains = str(params.get("name_contains")) if params.get("name_contains") is not None else None

        if kind == "files":
            return list_project_files(root, self.excludes, limit=limit)
        if kind == "symbols":
            if not rel_path:
                raise ValueError("path is required")
            return list_symbols(root, rel_path, prefer_tree_sitter=self.prefer_tree_sitter)
        if kind == "ast":
            if not rel_path:
                raise ValueError("path is required")
            return query_python_ast(root, rel_path, node_type=node_type, name_contains=name_contains, prefer_tree_sitter=self.prefer_tree_sitter)
        if kind == "validate":
            if not rel_path:
                raise ValueError("path is required")
            return validate_syntax(root, rel_path, prefer_tree_sitter=self.prefer_tree_sitter)
        if kind == "dependencies":
            if not rel_path:
                raise ValueError("path is required")
            return analyze_dependencies(root, rel_path)
        if kind == "complexity":
            if not rel_path:
                raise ValueError("path is required")
            return analyze_complexity(root, rel_path, prefer_tree_sitter=self.prefer_tree_sitter)
        if kind == "usage":
            if not symbol:
                raise ValueError("symbol is required")
            return find_symbol_usage(root, self.excludes, symbol=symbol, limit=limit)
        if kind == "stats":
            return project_stats(root, self.excludes)
        if kind == "graph":
            with Storage(self.db_path) as storage:
                workspace = str(self.config_data.get("workspace", "default"))
                return extract_graph_data(storage, workspace, root, self.excludes)
        raise ValueError(f"Unknown analysis kind: {kind}")

    def _memory_payload(self, memory_service: MemoryService, params: dict[str, list[str]], path: str) -> dict:
        workspace = self._workspace(params)
        if path == "/memory/status":
            return memory_service.status(workspace)
        if path == "/memory/search":
            query = params.get("query", [""])[0]
            layer = params.get("layer", ["summary"])[0]
            budget = int(params.get("budget", [str(self.config_data["memory"]["summary_budget_tokens"])])[0])  # type: ignore[index]
            top_k = int(params.get("top_k", ["8"])[0])
            return memory_service.search(workspace=workspace, query=query, layer=layer, budget_tokens=budget, max_results=top_k)
        if path.startswith("/memory/observations/"):
            observation_id = path.rsplit("/", 1)[-1]
            return memory_service.expand(observation_id)
        if path == "/memory/sessions":
            return {"workspace": workspace, "sessions": memory_service.list_sessions(workspace)}
        if path.startswith("/memory/sessions/"):
            session_id = path.rsplit("/", 1)[-1]
            return memory_service.get_session(session_id)
        if path.startswith("/memory/citations/"):
            target_id = path.rsplit("/", 1)[-1]
            return memory_service.citations(target_id)
        raise ValueError("Unknown memory endpoint")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        workspace = self._workspace(params)
        if self._requires_auth(parsed.path) and not self._authorized():
            self._unauthorized()
            return

        try:
            with Storage(self.db_path) as storage:
                memory_service = MemoryService(storage=storage, config=self.config_data)
                memory_service.capabilities()
                context = memory_service.start_session(
                    workspace=workspace,
                    project_root=self.default_root,
                    actor_surface="http",
                    command_name=parsed.path,
                    trigger_kind="http",
                ) if self.config_data.get("memory", {}).get("enabled", True) else None

                if parsed.path == "/search":
                    query = params.get("query", [""])[0]
                    include_global = params.get("include_global", ["true"])[0].lower() == "true"
                    mode = params.get("mode", ["hybrid"])[0].lower()
                    try:
                        top_k = max(1, int(params.get("top_k", ["5"])[0]))
                    except ValueError:
                        self.send_error(400, "top_k must be an integer")
                        return
                    if not query or not workspace:
                        self.send_error(400, "query and workspace are required")
                        return
                    if mode not in {"chunks", "symbols", "hybrid"}:
                        self.send_error(400, "mode must be one of: chunks, symbols, hybrid")
                        return
                    memory_payload = {"results": []}
                    if self.config_data.get("memory", {}).get("inject_on_query", True) and context is not None:
                        memory_payload = memory_service.inject(context, "server_request_completed", query)
                    _, scored, metrics = search_index(storage, query, workspace, include_global, top_k, mode)
                    payload = {
                        "query": query,
                        "workspace": workspace,
                        "metrics": metrics,
                        "results": [
                            {
                                "workspace": item.chunk.workspace,
                                "path": item.chunk.path,
                                "line_start": item.chunk.line_start,
                                "line_end": item.chunk.line_end,
                                "kind": item.chunk.source_kind,
                                "symbol": item.chunk.symbol_name,
                                "score": round(item.score, 4),
                                "token_count": item.chunk.token_count,
                                "snippet": item.chunk.text[:500],
                            }
                            for item in scored
                        ],
                        "memory": memory_payload,
                    }
                    self._json_response(200, payload)
                    if context is not None:
                        memory_service.capture_event(
                            context=context,
                            event_name="server_request_completed",
                            arguments_summary=query,
                            result_summary=f"search results={len(payload['results'])}",
                            token_metrics={"context_tokens": int(metrics["context_tokens"])},
                            metadata={"path": parsed.path},
                        )
                        memory_service.run_worker_once()
                        memory_service.end_session(context)
                    return

                if parsed.path.startswith("/analysis/"):
                    kind = parsed.path.split("/")[-1]
                    raw_params: dict[str, object] = {
                        "root": params.get("root", [None])[0],
                        "path": params.get("path", [None])[0],
                        "symbol": params.get("symbol", [""])[0],
                        "node_type": params.get("node_type", [None])[0],
                        "name_contains": params.get("name_contains", [None])[0],
                        "limit": int(params.get("limit", ["50"])[0]),
                    }
                    payload = self._analysis_payload(kind, raw_params)
                    if self.config_data.get("memory", {}).get("inject_on_analyze", True) and context is not None:
                        payload["memory"] = memory_service.inject(context, "analysis_executed", str(raw_params.get("path") or kind))
                    self._json_response(200, payload)
                    if context is not None:
                        memory_service.capture_event(
                            context=context,
                            event_name="analysis_executed",
                            arguments_summary=json.dumps(raw_params),
                            result_summary=f"analysis={kind}",
                            metadata={"path": parsed.path},
                        )
                        memory_service.run_worker_once()
                        memory_service.end_session(context)
                    return

                if parsed.path == "/memory/viewer":
                    self._html_response(render_viewer_page(workspace))
                    if context is not None:
                        memory_service.end_session(context)
                    return

                if parsed.path == "/memory/stream":
                    limit = int(self.config_data.get("memory", {}).get("viewer", {}).get("stream_buffer_size", 200))
                    self._sse_response(render_stream_payload(memory_service.recent_stream_events(workspace, limit=limit)))
                    if context is not None:
                        memory_service.end_session(context)
                    return

                if parsed.path.startswith("/memory/"):
                    payload = self._memory_payload(memory_service, params, parsed.path)
                    self._json_response(200, payload)
                    if context is not None:
                        memory_service.capture_event(
                            context=context,
                            event_name="server_request_completed",
                            arguments_summary=parsed.path,
                            result_summary="memory endpoint",
                            metadata={"path": parsed.path},
                        )
                        memory_service.run_worker_once()
                        memory_service.end_session(context)
                    return

                if context is not None:
                    memory_service.end_session(context)
                self.send_error(404, "Not Found")
        except ValueError as exc:
            self.send_error(400, str(exc))

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/mcp":
            self.send_error(404, "Not Found")
            return
        if self._requires_auth(self.path) and not self._authorized():
            self._unauthorized()
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            request = json.loads(raw)
        except Exception:
            self.send_error(400, "Invalid JSON body")
            return

        rpc_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})
        if not isinstance(params, dict):
            self._rpc_response(rpc_id, error={"code": -32602, "message": "Invalid params"})
            return

        try:
            with Storage(self.db_path) as storage:
                memory_service = MemoryService(storage=storage, config=self.config_data)
                memory_service.capabilities()
                workspace = str(params.get("workspace", self.config_data.get("workspace", "default")))
                context = memory_service.start_session(
                    workspace=workspace,
                    project_root=self.default_root,
                    actor_surface="mcp",
                    command_name=str(method),
                    trigger_kind="mcp",
                ) if self.config_data.get("memory", {}).get("enabled", True) else None

                if method == "initialize":
                    self._rpc_response(
                        rpc_id,
                        result={
                            "protocolVersion": "2024-11-05",
                            "serverInfo": {"name": "codeindex-sync", "version": "0.0.1"},
                            "capabilities": {"tools": {}},
                        },
                    )
                    if context is not None:
                        memory_service.end_session(context)
                    return

                if method == "tools/list":
                    self._rpc_response(rpc_id, result={"tools": self.MCP_TOOLS})
                    if context is not None:
                        memory_service.end_session(context)
                    return

                if method != "tools/call":
                    self._rpc_response(rpc_id, error={"code": -32601, "message": f"Method not found: {method}"})
                    if context is not None:
                        memory_service.end_session(context)
                    return

                name = params.get("name")
                arguments = params.get("arguments", {})
                if not isinstance(arguments, dict):
                    raise ValueError("arguments must be an object")

                if name == "codeindex_search":
                    query = str(arguments.get("query", ""))
                    workspace = str(arguments.get("workspace", ""))
                    top_k = max(1, int(arguments.get("top_k", 5)))
                    include_global = bool(arguments.get("include_global", True))
                    mode = str(arguments.get("mode", "hybrid")).lower()
                    if not query or not workspace:
                        raise ValueError("query and workspace are required")
                    memory_payload = {"results": []}
                    if self.config_data.get("memory", {}).get("inject_on_mcp", True) and context is not None:
                        memory_payload = memory_service.inject(context, "mcp_tool_called", query)
                    _, scored, metrics = search_index(storage, query, workspace, include_global, top_k, mode)
                    payload = {
                        "query": query,
                        "workspace": workspace,
                        "metrics": metrics,
                        "results": [
                            {
                                "workspace": item.chunk.workspace,
                                "path": item.chunk.path,
                                "line_start": item.chunk.line_start,
                                "line_end": item.chunk.line_end,
                                "kind": item.chunk.source_kind,
                                "symbol": item.chunk.symbol_name,
                                "score": round(item.score, 4),
                                "token_count": item.chunk.token_count,
                                "snippet": item.chunk.text[:500],
                            }
                            for item in scored
                        ],
                        "memory": memory_payload,
                    }
                elif name == "codeindex_analyze":
                    kind = str(arguments.get("kind", ""))
                    payload = self._analysis_payload(kind, arguments)
                    if self.config_data.get("memory", {}).get("inject_on_mcp", True) and context is not None:
                        payload["memory"] = memory_service.inject(context, "mcp_tool_called", str(arguments.get("path") or kind))
                elif name == "codeindex_memory_search":
                    payload = memory_service.search(
                        workspace=str(arguments.get("workspace", self.config_data.get("workspace", "default"))),
                        query=str(arguments.get("query", "")),
                        layer=str(arguments.get("layer", "summary")),
                        budget_tokens=int(arguments.get("budget", self.config_data["memory"]["summary_budget_tokens"])),  # type: ignore[index]
                        max_results=max(1, int(arguments.get("top_k", 8))),
                    )
                elif name == "codeindex_memory_expand":
                    payload = memory_service.expand(str(arguments.get("observation_id", "")))
                elif name == "codeindex_memory_session_list":
                    mem_workspace = str(arguments.get("workspace", self.config_data.get("workspace", "default")))
                    payload = {"workspace": mem_workspace, "sessions": memory_service.list_sessions(mem_workspace)}
                elif name == "codeindex_memory_session_show":
                    payload = memory_service.get_session(str(arguments.get("session_id", "")))
                elif name == "codeindex_memory_status":
                    mem_workspace = str(arguments.get("workspace", self.config_data.get("workspace", "default")))
                    payload = memory_service.status(mem_workspace)
                else:
                    self._rpc_response(rpc_id, error={"code": -32601, "message": f"Method tool not found: {name}"})
                    if context is not None:
                        memory_service.end_session(context)
                    return

                self._rpc_response(rpc_id, result={"content": [{"type": "text", "text": json.dumps(payload)}]})
                if context is not None:
                    memory_service.capture_event(
                        context=context,
                        event_name="mcp_tool_called",
                        arguments_summary=json.dumps({"tool": name, "arguments": arguments}),
                        result_summary=f"tool={name}",
                        metadata={"tool": name},
                    )
                    memory_service.run_worker_once()
                    memory_service.end_session(context)
        except ValueError as exc:
            self._rpc_response(rpc_id, error={"code": -32602, "message": str(exc)})
        except Exception as exc:  # pragma: no cover - defensive
            self._rpc_response(rpc_id, error={"code": -32000, "message": str(exc)})


def serve(
    db_path: Path,
    host: str,
    port: int,
    default_root: Path,
    excludes: list[str],
    prefer_tree_sitter: bool,
    config_data: dict[str, object],
    allow_remote: bool = False,
    auth_token: str | None = None,
    auth_token_header: str = "X-CodeIndex-Token",
) -> None:
    validate_bind_host(host, allow_remote)

    class Handler(SearchHandler):
        pass

    Handler.db_path = db_path
    Handler.default_root = default_root
    Handler.excludes = excludes
    Handler.prefer_tree_sitter = prefer_tree_sitter
    Handler.config_data = config_data
    Handler.auth_token = auth_token.strip() if isinstance(auth_token, str) else None
    Handler.auth_token_header = auth_token_header
    server = ThreadingHTTPServer((host, port), Handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()
