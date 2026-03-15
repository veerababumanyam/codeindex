from __future__ import annotations

import json
from pathlib import Path
from secrets import compare_digest
from typing import Annotated, Any

from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
import uvicorn

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

app = FastAPI()

@app.exception_handler(ValueError)
async def value_error_exception_handler(request: Request, exc: ValueError):
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )

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


def validate_bind_host(host: str, allow_remote: bool) -> None:
    if not allow_remote and not is_loopback_host(host):
        raise ValueError(
            f"Refusing to bind to non-loopback host '{host}' without explicit remote opt-in. "
            "Set server.allow_remote: true or pass --allow-remote."
        )


async def verify_auth(request: Request):
    auth_token = getattr(request.app.state, "auth_token", None)
    if not auth_token:
        return
    
    header_name = getattr(request.app.state, "auth_token_header", "X-CodeIndex-Token")
    provided = request.headers.get(header_name)
    if not provided or not compare_digest(provided, auth_token):
        raise HTTPException(
            status_code=401,
            detail={
                "error": "Unauthorized",
                "message": f"Provide the configured API token in the {header_name} header.",
            }
        )


async def get_storage(request: Request):
    db_path = request.app.state.db_path
    async with await Storage.create(db_path) as storage:
        yield storage


def get_workspace(request: Request, workspace: str | None = None) -> str:
    if workspace:
        return workspace
    return str(request.app.state.config_data.get("workspace", "default"))


def trusted_analysis_root(request: Request, root: str | None = None) -> Path:
    if root is not None:
        candidate = Path(root).resolve()
        if candidate != request.app.state.default_root:
            raise HTTPException(status_code=400, detail="root overrides are not allowed for server analysis")
    return request.app.state.default_root


async def get_analysis_payload(request: Request, storage: Storage, kind: str, params: dict[str, Any]) -> dict:
    root = trusted_analysis_root(request, params.get("root"))
    limit = max(1, int(params.get("limit", 50)))
    rel_path = ""
    raw_path = params.get("path")
    if isinstance(raw_path, str) and raw_path.strip():
        rel_path = validate_relative_path(raw_path)
    symbol = str(params.get("symbol", "")) if params.get("symbol") is not None else ""
    node_type = str(params.get("node_type")) if params.get("node_type") is not None else None
    name_contains = str(params.get("name_contains")) if params.get("name_contains") is not None else None
    
    excludes = request.app.state.excludes
    prefer_tree_sitter = request.app.state.prefer_tree_sitter

    if kind == "files":
        return list_project_files(root, excludes, limit=limit)
    if kind == "symbols":
        if not rel_path:
            raise HTTPException(status_code=400, detail="path is required")
        return list_symbols(root, rel_path, prefer_tree_sitter=prefer_tree_sitter)
    if kind == "ast":
        if not rel_path:
            raise HTTPException(status_code=400, detail="path is required")
        return query_python_ast(root, rel_path, node_type=node_type, name_contains=name_contains, prefer_tree_sitter=prefer_tree_sitter)
    if kind == "validate":
        if not rel_path:
            raise HTTPException(status_code=400, detail="path is required")
        return validate_syntax(root, rel_path, prefer_tree_sitter=prefer_tree_sitter)
    if kind == "dependencies":
        if not rel_path:
            raise HTTPException(status_code=400, detail="path is required")
        return analyze_dependencies(root, rel_path)
    if kind == "complexity":
        if not rel_path:
            raise HTTPException(status_code=400, detail="path is required")
        return analyze_complexity(root, rel_path, prefer_tree_sitter=prefer_tree_sitter)
    if kind == "usage":
        if not symbol:
            raise HTTPException(status_code=400, detail="symbol is required")
        return find_symbol_usage(root, excludes, symbol=symbol, limit=limit)
    if kind == "stats":
        return project_stats(root, excludes)
    if kind == "graph":
        workspace = get_workspace(request)
        return extract_graph_data(storage, workspace, root, excludes)
    raise HTTPException(status_code=400, detail=f"Unknown analysis kind: {kind}")


@app.get("/search", dependencies=[Depends(verify_auth)])
async def search(
    request: Request,
    query: str,
    storage: Annotated[Storage, Depends(get_storage)],
    workspace: str | None = None,
    include_global: bool = True,
    mode: str = "hybrid",
    top_k: int = 5,
):
    workspace_val = get_workspace(request, workspace)
    if mode not in {"chunks", "symbols", "hybrid"}:
        raise HTTPException(status_code=400, detail="mode must be one of: chunks, symbols, hybrid")
    
    memory_service = MemoryService(storage=storage, config=request.app.state.config_data)
    await memory_service.capabilities()
    
    context = None
    if request.app.state.config_data.get("memory", {}).get("enabled", True):
        context = await memory_service.start_session(
            workspace=workspace_val,
            project_root=request.app.state.default_root,
            actor_surface="http",
            command_name="/search",
            trigger_kind="http",
        )
    
    try:
        memory_payload = {"results": []}
        if request.app.state.config_data.get("memory", {}).get("inject_on_query", True) and context is not None:
            memory_payload = await memory_service.inject(context, "server_request_completed", query)
        
        _, scored, metrics = await search_index(storage, query, workspace_val, include_global, top_k, mode)
        
        payload = {
            "query": query,
            "workspace": workspace_val,
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
        
        if context is not None:
            await memory_service.capture_event(
                context=context,
                event_name="server_request_completed",
                arguments_summary=query,
                result_summary=f"search results={len(payload['results'])}",
                token_metrics={"context_tokens": int(metrics["context_tokens"])},
                metadata={"path": "/search"},
            )
            await memory_service.run_worker_once()
            await memory_service.end_session(context)
            
        return payload
    except Exception as e:
        if context is not None:
            await memory_service.end_session(context)
        raise e


@app.get("/analysis/{kind}", dependencies=[Depends(verify_auth)])
async def analysis(
    kind: str,
    request: Request,
    storage: Annotated[Storage, Depends(get_storage)],
    root: str | None = None,
    path: str | None = None,
    symbol: str = "",
    node_type: str | None = None,
    name_contains: str | None = None,
    limit: int = 50,
):
    params = {
        "root": root,
        "path": path,
        "symbol": symbol,
        "node_type": node_type,
        "name_contains": name_contains,
        "limit": limit,
    }
    
    memory_service = MemoryService(storage=storage, config=request.app.state.config_data)
    await memory_service.capabilities()
    
    workspace_val = get_workspace(request)
    context = None
    if request.app.state.config_data.get("memory", {}).get("enabled", True):
        context = await memory_service.start_session(
            workspace=workspace_val,
            project_root=request.app.state.default_root,
            actor_surface="http",
            command_name=f"/analysis/{kind}",
            trigger_kind="http",
        )
        
    try:
        payload = await get_analysis_payload(request, storage, kind, params)
        
        if request.app.state.config_data.get("memory", {}).get("inject_on_analyze", True) and context is not None:
            payload["memory"] = await memory_service.inject(context, "analysis_executed", str(params.get("path") or kind))
            
        if context is not None:
            await memory_service.capture_event(
                context=context,
                event_name="analysis_executed",
                arguments_summary=json.dumps(params),
                result_summary=f"analysis={kind}",
                metadata={"path": f"/analysis/{kind}"},
            )
            await memory_service.run_worker_once()
            await memory_service.end_session(context)
            
        return payload
    except Exception as e:
        if context is not None:
            await memory_service.end_session(context)
        raise e


@app.get("/memory/viewer")
async def memory_viewer(request: Request, workspace: str | None = None):
    workspace_val = get_workspace(request, workspace)
    return HTMLResponse(content=render_viewer_page(workspace_val))


@app.get("/memory/stream")
async def memory_stream(request: Request, workspace: str | None = None):
    workspace_val = get_workspace(request, workspace)
    async with await Storage.create(request.app.state.db_path) as storage:
        memory_service = MemoryService(storage=storage, config=request.app.state.config_data)
        limit = int(request.app.state.config_data.get("memory", {}).get("viewer", {}).get("stream_buffer_size", 200))
        events = await memory_service.recent_stream_events(workspace_val, limit=limit)
        return StreamingResponse(iter([render_stream_payload(events)]), media_type="text/event-stream")


@app.get("/memory/status", dependencies=[Depends(verify_auth)])
async def memory_status(request: Request, storage: Annotated[Storage, Depends(get_storage)], workspace: str | None = None):
    workspace_val = get_workspace(request, workspace)
    memory_service = MemoryService(storage=storage, config=request.app.state.config_data)
    return await memory_service.status(workspace_val)


@app.get("/memory/sessions", dependencies=[Depends(verify_auth)])
async def memory_sessions(request: Request, storage: Annotated[Storage, Depends(get_storage)], workspace: str | None = None):
    workspace_val = get_workspace(request, workspace)
    memory_service = MemoryService(storage=storage, config=request.app.state.config_data)
    return {"workspace": workspace_val, "sessions": await memory_service.list_sessions(workspace_val)}


@app.get("/memory/sessions/{session_id}", dependencies=[Depends(verify_auth)])
async def memory_session_get(session_id: str, request: Request, storage: Annotated[Storage, Depends(get_storage)]):
    memory_service = MemoryService(storage=storage, config=request.app.state.config_data)
    return await memory_service.get_session(session_id)


@app.get("/memory/observations/{observation_id}", dependencies=[Depends(verify_auth)])
async def memory_observation_get(observation_id: str, request: Request, storage: Annotated[Storage, Depends(get_storage)]):
    memory_service = MemoryService(storage=storage, config=request.app.state.config_data)
    return await memory_service.expand(observation_id)


@app.get("/memory/citations/{target_id}", dependencies=[Depends(verify_auth)])
async def memory_citations_get(target_id: str, request: Request, storage: Annotated[Storage, Depends(get_storage)]):
    memory_service = MemoryService(storage=storage, config=request.app.state.config_data)
    return await memory_service.citations(target_id)


@app.get("/memory/search", dependencies=[Depends(verify_auth)])
async def memory_search(
    request: Request,
    storage: Annotated[Storage, Depends(get_storage)],
    query: str = "",
    workspace: str | None = None,
    layer: str = "summary",
    budget: int | None = None,
    top_k: int = 8,
):
    workspace_val = get_workspace(request, workspace)
    if budget is None:
        budget = int(request.app.state.config_data["memory"]["summary_budget_tokens"])
    memory_service = MemoryService(storage=storage, config=request.app.state.config_data)
    return await memory_service.search(workspace=workspace_val, query=query, layer=layer, budget_tokens=budget, max_results=top_k)


@app.post("/mcp", dependencies=[Depends(verify_auth)])
async def mcp_endpoint(request: Request, storage: Annotated[Storage, Depends(get_storage)]):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    
    rpc_id = body.get("id")
    method = body.get("method")
    params = body.get("params", {})
    
    if not isinstance(params, dict):
        return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32602, "message": "Invalid params"}}

    memory_service = MemoryService(storage=storage, config=request.app.state.config_data)
    await memory_service.capabilities()
    
    workspace_val = str(params.get("workspace", request.app.state.config_data.get("workspace", "default")))
    context = None
    if request.app.state.config_data.get("memory", {}).get("enabled", True):
        context = await memory_service.start_session(
            workspace=workspace_val,
            project_root=request.app.state.default_root,
            actor_surface="mcp",
            command_name=str(method),
            trigger_kind="mcp",
        )
    
    try:
        if method == "initialize":
            result: Any = {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "codeindex-sync", "version": "0.0.1"},
                "capabilities": {"tools": {}},
            }
        elif method == "tools/list":
            result = {"tools": MCP_TOOLS}
        elif method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments", {})
            if not isinstance(arguments, dict):
                raise ValueError("arguments must be an object")
            
            payload = None
            if name == "codeindex_search":
                query = str(arguments.get("query", ""))
                mcp_workspace = str(arguments.get("workspace", ""))
                top_k = max(1, int(arguments.get("top_k", 5)))
                include_global = bool(arguments.get("include_global", True))
                mode = str(arguments.get("mode", "hybrid")).lower()
                if not query or not mcp_workspace:
                    raise ValueError("query and workspace are required")
                
                memory_payload = {"results": []}
                if request.app.state.config_data.get("memory", {}).get("inject_on_mcp", True) and context is not None:
                    memory_payload = await memory_service.inject(context, "mcp_tool_called", query)
                
                _, scored, metrics = await search_index(storage, query, mcp_workspace, include_global, top_k, mode)
                payload = {
                    "query": query,
                    "workspace": mcp_workspace,
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
                payload = await get_analysis_payload(request, storage, kind, arguments)
                if request.app.state.config_data.get("memory", {}).get("inject_on_mcp", True) and context is not None:
                    payload["memory"] = await memory_service.inject(context, "mcp_tool_called", str(arguments.get("path") or kind))
            elif name == "codeindex_memory_search":
                payload = await memory_service.search(
                    workspace=str(arguments.get("workspace", request.app.state.config_data.get("workspace", "default"))),
                    query=str(arguments.get("query", "")),
                    layer=str(arguments.get("layer", "summary")),
                    budget_tokens=int(arguments.get("budget", request.app.state.config_data["memory"]["summary_budget_tokens"])),
                    max_results=max(1, int(arguments.get("top_k", 8))),
                )
            elif name == "codeindex_memory_expand":
                payload = await memory_service.expand(str(arguments.get("observation_id", "")))
            elif name == "codeindex_memory_session_list":
                mem_workspace = str(arguments.get("workspace", request.app.state.config_data.get("workspace", "default")))
                payload = {"workspace": mem_workspace, "sessions": await memory_service.list_sessions(mem_workspace)}
            elif name == "codeindex_memory_session_show":
                payload = await memory_service.get_session(str(arguments.get("session_id", "")))
            elif name == "codeindex_memory_status":
                mem_workspace = str(arguments.get("workspace", request.app.state.config_data.get("workspace", "default")))
                payload = await memory_service.status(mem_workspace)
            else:
                return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32601, "message": f"Method tool not found: {name}"}}
            
            result = {"content": [{"type": "text", "text": json.dumps(payload)}]}
            
            if context is not None:
                await memory_service.capture_event(
                    context=context,
                    event_name="mcp_tool_called",
                    arguments_summary=json.dumps({"tool": name, "arguments": arguments}),
                    result_summary=f"tool={name}",
                    metadata={"tool": name},
                )
                await memory_service.run_worker_once()
        else:
            return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}
        
        if context is not None:
            await memory_service.end_session(context)
        
        return {"jsonrpc": "2.0", "id": rpc_id, "result": result}
        
    except ValueError as exc:
        if context is not None:
            await memory_service.end_session(context)
        return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32602, "message": str(exc)}}
    except HTTPException as exc:
        if context is not None:
            await memory_service.end_session(context)
        code = -32602 if exc.status_code == 400 else -32000
        return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": str(exc.detail)}}
    except Exception as exc:
        if context is not None:
            await memory_service.end_session(context)
        return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32000, "message": str(exc)}}


def serve(
    db_path: Path,
    host: str,
    port: int,
    default_root: Path,
    excludes: list[str],
    prefer_tree_sitter: bool,
    config_data: dict[str, Any],
    allow_remote: bool = False,
    auth_token: str | None = None,
    auth_token_header: str = "X-CodeIndex-Token",
) -> None:
    validate_bind_host(host, allow_remote)
    
    app.state.db_path = db_path
    app.state.default_root = default_root
    app.state.excludes = excludes
    app.state.prefer_tree_sitter = prefer_tree_sitter
    app.state.config_data = config_data
    app.state.auth_token = auth_token.strip() if isinstance(auth_token, str) else None
    app.state.auth_token_header = auth_token_header
    
    uvicorn.run(app, host=host, port=port)
