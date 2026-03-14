from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Callable

from .analysis import (
    analyze_complexity,
    analyze_dependencies,
    find_symbol_usage,
    list_project_files,
    list_symbols,
    project_stats,
    query_python_ast,
    validate_syntax,
)
from .config import DEFAULT_CONFIG, load_config, save_config, set_config_value
from .indexer import sync_workspace
from .memory_service import MemoryContext, MemoryService
from .search import search_index
from .server import serve, validate_bind_host
from .storage import Storage


def parse_value(raw: str) -> Any:
    lowered = raw.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        return raw


def db_path(base_dir: Path) -> Path:
    return base_dir / ".codeindex" / "index.db"


def _json_print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2))


def _memory_service(storage: Storage, loaded_config: dict[str, Any]) -> MemoryService:
    service = MemoryService(storage=storage, config=loaded_config)
    service.capabilities()
    return service


def _start_memory_context(
    memory_service: MemoryService,
    workspace: str,
    project_root: Path,
    command_name: str,
) -> MemoryContext | None:
    if not memory_service.enabled():
        return None
    return memory_service.start_session(
        workspace=workspace,
        project_root=project_root,
        actor_surface="cli",
        command_name=command_name,
        trigger_kind="cli",
    )


def _finish_memory_context(
    memory_service: MemoryService,
    context: MemoryContext | None,
    event_name: str,
    arguments_summary: str,
    result_summary: str,
    error_summary: str | None = None,
    token_metrics: dict[str, int | str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if context is None:
        return
    memory_service.capture_event(
        context=context,
        event_name=event_name,
        arguments_summary=arguments_summary,
        result_summary=result_summary,
        error_summary=error_summary,
        token_metrics=token_metrics,
        metadata=metadata,
    )
    memory_service.run_worker_once()
    memory_service.end_session(context)


def _run_sync_once(
    storage: Storage,
    loaded_config: dict[str, Any],
    workspace_override: str | None = None,
) -> dict[str, int]:
    workspace = workspace_override or loaded_config.get("workspace", "default")
    project_root = Path(loaded_config["paths"]["project_root"])
    excludes = loaded_config.get("excludes", [])
    chunk_size = int(loaded_config["indexing"].get("chunk_size", 800))
    chunk_overlap = int(loaded_config["indexing"].get("chunk_overlap", 120))

    stats = sync_workspace(
        storage=storage,
        workspace=workspace,
        root=project_root,
        excludes=excludes,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    if loaded_config["query"].get("include_global_docs", True):
        for gdir in loaded_config["paths"].get("global_docs", []):
            p = Path(gdir)
            if p.exists():
                sync_workspace(storage, "global", p, excludes, chunk_size, chunk_overlap)

    return stats.__dict__


def cmd_init(args: argparse.Namespace) -> int:
    config_path = Path(args.config)
    if config_path.exists() and not args.force:
        print(f"Config already exists at {config_path}. Use --force to overwrite.")
        return 1

    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    cfg["workspace"] = args.workspace
    cfg["paths"]["project_root"] = str(Path(args.path).resolve())
    if args.global_docs:
        cfg["paths"]["global_docs"] = [str(Path(p).resolve()) for p in args.global_docs]

    config_path.parent.mkdir(parents=True, exist_ok=True)
    save_config(config_path, cfg)

    storage = Storage(db_path(config_path.parent.resolve()))
    storage.close()
    print(f"Initialized CodeIndex at {config_path}")
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    loaded = load_config(Path(args.config))
    try:
        set_config_value(loaded.data, args.key, parse_value(args.value))
    except (KeyError, ValueError) as exc:
        print(str(exc))
        return 1
    save_config(loaded.path, loaded.data)
    print(f"Updated {args.key}")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    config_path = Path(args.config)
    loaded = load_config(config_path)
    database_path = db_path(config_path.parent.resolve())
    workspace = args.workspace or loaded.data.get("workspace", "default")
    project_root = Path(loaded.data["paths"]["project_root"]).resolve()

    with Storage(database_path) as storage:
        memory_service = _memory_service(storage, loaded.data)
        context = _start_memory_context(memory_service, workspace, project_root, "sync")
        stats = _run_sync_once(storage, loaded.data, workspace_override=args.workspace)
        _json_print(stats)
        _finish_memory_context(
            memory_service,
            context,
            event_name="sync_completed",
            arguments_summary=f"sync workspace={workspace}",
            result_summary=f"indexed={stats['indexed']} deleted={stats['deleted']}",
            token_metrics={"indexed": stats["indexed"], "deleted": stats["deleted"]},
            metadata={"stats": stats},
        )

        if args.watch:
            print(f"Watch mode enabled. Polling every {args.interval} seconds. Ctrl+C to stop.")
            try:
                while True:
                    time.sleep(args.interval)
                    next_stats = _run_sync_once(storage, loaded.data, workspace_override=args.workspace)
                    if next_stats["indexed"] or next_stats["deleted"]:
                        _json_print(next_stats)
                        memory_service.run_worker_once()
            except KeyboardInterrupt:
                print("Stopping watch mode")
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    loaded = load_config(Path(args.config))
    workspace = args.workspace or loaded.data.get("workspace", "default")
    if loaded.data["query"].get("require_workspace", True) and not workspace:
        print("Workspace is required")
        return 1

    include_global = args.include_global or loaded.data["query"].get("include_global_docs", True)
    top_k = args.top_k or int(loaded.data["query"].get("top_k", 5))
    mode = args.mode or loaded.data["query"].get("mode", "hybrid")
    project_root = Path(loaded.data["paths"]["project_root"]).resolve()

    with Storage(db_path(Path(args.config).parent.resolve())) as storage:
        memory_service = _memory_service(storage, loaded.data)
        context = _start_memory_context(memory_service, workspace, project_root, "query")
        memory_payload = {"results": []}
        if loaded.data["memory"].get("inject_on_query", True) and context is not None:
            memory_payload = memory_service.inject(context, "query_executed", args.query)
        _, scored, metrics = search_index(storage, args.query, workspace, include_global, top_k, mode)

        results = [
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
        ]
        payload = {
            "query": args.query,
            "workspace": workspace,
            "metrics": metrics,
            "results": results,
            "memory": memory_payload,
        }
        _json_print(payload)
        _finish_memory_context(
            memory_service,
            context,
            event_name="query_executed",
            arguments_summary=args.query,
            result_summary=f"results={len(results)} mode={mode}",
            token_metrics={"context_tokens": int(metrics["context_tokens"])},
            metadata={"mode": mode, "memory": memory_payload},
        )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    loaded = load_config(Path(args.config))
    workspace = loaded.data.get("workspace", "default")
    project_root = Path(loaded.data["paths"]["project_root"]).resolve()
    with Storage(db_path(Path(args.config).parent.resolve())) as storage:
        memory_service = _memory_service(storage, loaded.data)
        context = _start_memory_context(memory_service, workspace, project_root, "status")
        counts = storage.counts()
        counts["capabilities"] = {
            "vector": storage.capability_summary(),
            "memory": memory_service.capability_summary(),
        }
        _json_print(counts)
        _finish_memory_context(
            memory_service,
            context,
            event_name="command_end",
            arguments_summary="status",
            result_summary=f"files={counts['files']} chunks={counts['chunks']}",
            metadata={"counts": counts},
        )
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    loaded = load_config(Path(args.config))
    database_path = db_path(Path(args.config).parent.resolve())
    server_cfg = loaded.data["server"]
    host = args.host or str(server_cfg["host"])
    port = args.port or int(server_cfg["port"])
    allow_remote = bool(args.allow_remote or server_cfg.get("allow_remote", False))
    auth_token = args.auth_token if args.auth_token is not None else server_cfg.get("auth_token")
    auth_token_header = str(server_cfg.get("auth_token_header", "X-CodeIndex-Token"))
    with Storage(database_path):
        pass
    validate_bind_host(host, allow_remote)
    print(f"Serving on {host}:{port}")
    serve(
        db_path=database_path,
        host=host,
        port=port,
        default_root=Path(loaded.data["paths"]["project_root"]).resolve(),
        excludes=list(loaded.data.get("excludes", [])),
        prefer_tree_sitter=bool(loaded.data.get("analysis", {}).get("prefer_tree_sitter", True)),
        config_data=loaded.data,
        allow_remote=allow_remote,
        auth_token=str(auth_token) if auth_token is not None else None,
        auth_token_header=auth_token_header,
    )
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    loaded = load_config(Path(args.config))
    root = Path(args.root or loaded.data["paths"]["project_root"]).resolve()
    excludes = list(loaded.data.get("excludes", []))
    prefer_tree_sitter = bool(loaded.data.get("analysis", {}).get("prefer_tree_sitter", True))
    workspace = loaded.data.get("workspace", "default")

    with Storage(db_path(Path(args.config).parent.resolve())) as storage:
        memory_service = _memory_service(storage, loaded.data)
        context = _start_memory_context(memory_service, workspace, root, "analyze")
        memory_payload = {"results": []}
        if loaded.data["memory"].get("inject_on_analyze", True) and context is not None:
            injection_query = args.path or args.symbol or args.kind
            memory_payload = memory_service.inject(context, "analysis_executed", injection_query)

        kind = args.kind
        if kind == "files":
            payload = list_project_files(root, excludes, limit=args.limit)
        elif kind == "symbols":
            if not args.path:
                print("--path is required for symbols analysis")
                return 1
            payload = list_symbols(root, args.path, prefer_tree_sitter=prefer_tree_sitter)
        elif kind == "ast":
            if not args.path:
                print("--path is required for ast analysis")
                return 1
            payload = query_python_ast(
                root,
                args.path,
                node_type=args.node_type,
                name_contains=args.name_contains,
                prefer_tree_sitter=prefer_tree_sitter,
            )
        elif kind == "validate":
            if not args.path:
                print("--path is required for validate analysis")
                return 1
            payload = validate_syntax(root, args.path, prefer_tree_sitter=prefer_tree_sitter)
        elif kind == "dependencies":
            if not args.path:
                print("--path is required for dependencies analysis")
                return 1
            payload = analyze_dependencies(root, args.path)
        elif kind == "complexity":
            if not args.path:
                print("--path is required for complexity analysis")
                return 1
            payload = analyze_complexity(root, args.path, prefer_tree_sitter=prefer_tree_sitter)
        elif kind == "usage":
            if not args.symbol:
                print("--symbol is required for usage analysis")
                return 1
            payload = find_symbol_usage(root, excludes, args.symbol, limit=args.limit)
        elif kind == "stats":
            payload = project_stats(root, excludes)
        else:
            print(f"Unknown analysis kind: {kind}")
            return 1

        payload["memory"] = memory_payload
        _json_print(payload)
        _finish_memory_context(
            memory_service,
            context,
            event_name="analysis_executed",
            arguments_summary=json.dumps({"kind": kind, "path": args.path, "symbol": args.symbol}),
            result_summary=f"analysis={kind}",
            metadata={"kind": kind, "memory": memory_payload},
        )
    return 0


def cmd_memory_status(args: argparse.Namespace) -> int:
    loaded = load_config(Path(args.config))
    workspace = args.workspace or loaded.data.get("workspace", "default")
    project_root = Path(loaded.data["paths"]["project_root"]).resolve()
    with Storage(db_path(Path(args.config).parent.resolve())) as storage:
        memory_service = _memory_service(storage, loaded.data)
        context = _start_memory_context(memory_service, workspace, project_root, "memory_status")
        payload = memory_service.status(workspace)
        _json_print(payload)
        _finish_memory_context(
            memory_service,
            context,
            event_name="command_end",
            arguments_summary=f"memory status workspace={workspace}",
            result_summary=f"sessions={payload['sessions']} observations={payload['observations']}",
            metadata={"status": payload},
        )
    return 0


def cmd_memory_search(args: argparse.Namespace) -> int:
    loaded = load_config(Path(args.config))
    workspace = args.workspace or loaded.data.get("workspace", "default")
    project_root = Path(loaded.data["paths"]["project_root"]).resolve()
    with Storage(db_path(Path(args.config).parent.resolve())) as storage:
        memory_service = _memory_service(storage, loaded.data)
        context = _start_memory_context(memory_service, workspace, project_root, "memory_search")
        payload = memory_service.search(
            workspace=workspace,
            query=args.query,
            layer=args.layer,
            budget_tokens=args.budget,
            max_results=args.top_k,
        )
        _json_print(payload)
        _finish_memory_context(
            memory_service,
            context,
            event_name="search_executed",
            arguments_summary=args.query,
            result_summary=f"memory_results={len(payload['results'])}",
            metadata={"layer": payload["layer"]},
        )
    return 0


def cmd_memory_expand(args: argparse.Namespace) -> int:
    loaded = load_config(Path(args.config))
    workspace = loaded.data.get("workspace", "default")
    project_root = Path(loaded.data["paths"]["project_root"]).resolve()
    with Storage(db_path(Path(args.config).parent.resolve())) as storage:
        memory_service = _memory_service(storage, loaded.data)
        context = _start_memory_context(memory_service, workspace, project_root, "memory_expand")
        payload = memory_service.expand(args.observation_id)
        _json_print(payload)
        _finish_memory_context(
            memory_service,
            context,
            event_name="search_executed",
            arguments_summary=args.observation_id,
            result_summary="memory expand",
        )
    return 0


def cmd_memory_session_list(args: argparse.Namespace) -> int:
    loaded = load_config(Path(args.config))
    workspace = args.workspace or loaded.data.get("workspace", "default")
    with Storage(db_path(Path(args.config).parent.resolve())) as storage:
        memory_service = _memory_service(storage, loaded.data)
        payload = {"workspace": workspace, "sessions": memory_service.list_sessions(workspace)}
        _json_print(payload)
    return 0


def cmd_memory_session_show(args: argparse.Namespace) -> int:
    loaded = load_config(Path(args.config))
    with Storage(db_path(Path(args.config).parent.resolve())) as storage:
        memory_service = _memory_service(storage, loaded.data)
        payload = memory_service.get_session(args.session_id)
        _json_print(payload)
    return 0


def cmd_memory_citations(args: argparse.Namespace) -> int:
    loaded = load_config(Path(args.config))
    with Storage(db_path(Path(args.config).parent.resolve())) as storage:
        memory_service = _memory_service(storage, loaded.data)
        payload = memory_service.citations(args.target_id)
        _json_print(payload)
    return 0


def cmd_memory_viewer(args: argparse.Namespace) -> int:
    loaded = load_config(Path(args.config))
    viewer_cfg = loaded.data["memory"]["viewer"]
    server_cfg = loaded.data["server"]
    host = args.host or viewer_cfg["host"]
    port = args.port or int(viewer_cfg["port"])
    allow_remote = bool(args.allow_remote or server_cfg.get("allow_remote", False))
    auth_token = args.auth_token if args.auth_token is not None else server_cfg.get("auth_token")
    auth_token_header = str(server_cfg.get("auth_token_header", "X-CodeIndex-Token"))
    database_path = db_path(Path(args.config).parent.resolve())
    with Storage(database_path):
        pass
    validate_bind_host(host, allow_remote)
    print(f"Serving memory viewer on {host}:{port}")
    serve(
        db_path=database_path,
        host=host,
        port=port,
        default_root=Path(loaded.data["paths"]["project_root"]).resolve(),
        excludes=list(loaded.data.get("excludes", [])),
        prefer_tree_sitter=bool(loaded.data.get("analysis", {}).get("prefer_tree_sitter", True)),
        config_data=loaded.data,
        allow_remote=allow_remote,
        auth_token=str(auth_token) if auth_token is not None else None,
        auth_token_header=auth_token_header,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="codeindex", description="Local-first code indexing, analysis, and memory")
    p.add_argument("--config", default="codeindex.yaml", help="Path to config file")
    sp = p.add_subparsers(dest="cmd", required=True)

    p_init = sp.add_parser("init")
    p_init.add_argument("--path", required=True)
    p_init.add_argument("--workspace", default="default")
    p_init.add_argument("--global-docs", nargs="*")
    p_init.add_argument("--force", action="store_true")
    p_init.set_defaults(func=cmd_init)

    p_cfg = sp.add_parser("config")
    p_cfg.add_argument("key")
    p_cfg.add_argument("value")
    p_cfg.set_defaults(func=cmd_config)

    p_sync = sp.add_parser("sync")
    p_sync.add_argument("--workspace")
    p_sync.add_argument("--watch", action="store_true")
    p_sync.add_argument("--interval", type=float, default=2.0)
    p_sync.set_defaults(func=cmd_sync)

    p_query = sp.add_parser("query")
    p_query.add_argument("query")
    p_query.add_argument("--workspace")
    p_query.add_argument("--top-k", type=int)
    p_query.add_argument("--include-global", action="store_true")
    p_query.add_argument("--mode", choices=["chunks", "symbols", "hybrid"])
    p_query.set_defaults(func=cmd_query)

    p_status = sp.add_parser("status")
    p_status.set_defaults(func=cmd_status)

    p_serve = sp.add_parser("serve")
    p_serve.add_argument("--host")
    p_serve.add_argument("--port", type=int)
    p_serve.add_argument("--allow-remote", action="store_true")
    p_serve.add_argument("--auth-token")
    p_serve.set_defaults(func=cmd_serve)

    p_analyze = sp.add_parser("analyze")
    p_analyze.add_argument(
        "kind",
        choices=["ast", "validate", "files", "symbols", "dependencies", "complexity", "usage", "stats"],
        help="Analysis operation to run",
    )
    p_analyze.add_argument("--root", help="Project root path override")
    p_analyze.add_argument("--path", help="Relative file path for file-scoped analysis")
    p_analyze.add_argument("--symbol", help="Symbol name for usage analysis")
    p_analyze.add_argument("--node-type", help="AST node type filter, e.g. FunctionDef")
    p_analyze.add_argument("--name-contains", help="AST node name substring filter")
    p_analyze.add_argument("--limit", type=int, default=50, help="Max rows for list/usage outputs")
    p_analyze.set_defaults(func=cmd_analyze)

    p_memory = sp.add_parser("memory")
    memory_sp = p_memory.add_subparsers(dest="memory_cmd", required=True)

    p_memory_status = memory_sp.add_parser("status")
    p_memory_status.add_argument("--workspace")
    p_memory_status.set_defaults(func=cmd_memory_status)

    p_memory_search = memory_sp.add_parser("search")
    p_memory_search.add_argument("query")
    p_memory_search.add_argument("--workspace")
    p_memory_search.add_argument("--layer", choices=["summary", "expanded", "full"], default="summary")
    p_memory_search.add_argument("--budget", type=int)
    p_memory_search.add_argument("--top-k", type=int, default=8)
    p_memory_search.set_defaults(func=cmd_memory_search)

    p_memory_expand = memory_sp.add_parser("expand")
    p_memory_expand.add_argument("observation_id")
    p_memory_expand.set_defaults(func=cmd_memory_expand)

    p_memory_session = memory_sp.add_parser("session")
    memory_session_sp = p_memory_session.add_subparsers(dest="session_cmd", required=True)
    p_memory_session_list = memory_session_sp.add_parser("list")
    p_memory_session_list.add_argument("--workspace")
    p_memory_session_list.set_defaults(func=cmd_memory_session_list)
    p_memory_session_show = memory_session_sp.add_parser("show")
    p_memory_session_show.add_argument("session_id")
    p_memory_session_show.set_defaults(func=cmd_memory_session_show)

    p_memory_citations = memory_sp.add_parser("citations")
    p_memory_citations.add_argument("target_id")
    p_memory_citations.set_defaults(func=cmd_memory_citations)

    p_memory_viewer = memory_sp.add_parser("viewer")
    p_memory_viewer.add_argument("--host")
    p_memory_viewer.add_argument("--port", type=int)
    p_memory_viewer.add_argument("--allow-remote", action="store_true")
    p_memory_viewer.add_argument("--auth-token")
    p_memory_viewer.set_defaults(func=cmd_memory_viewer)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (RuntimeError, ValueError) as exc:
        print(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
