from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from .config import DEFAULT_CONFIG, load_config, save_config, set_config_value
from .embedding import cosine_similarity, embed_text
from .indexer import sync_workspace
from .server import serve
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


def _run_sync_once(config_path: Path, workspace_override: str | None = None) -> dict[str, int]:
    loaded = load_config(config_path)
    workspace = workspace_override or loaded.data.get("workspace", "default")
    project_root = Path(loaded.data["paths"]["project_root"])
    excludes = loaded.data.get("excludes", [])
    chunk_size = int(loaded.data["indexing"].get("chunk_size", 800))
    chunk_overlap = int(loaded.data["indexing"].get("chunk_overlap", 120))

    storage = Storage(db_path(config_path.parent.resolve()))
    stats = sync_workspace(
        storage=storage,
        workspace=workspace,
        root=project_root,
        excludes=excludes,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    if loaded.data["query"].get("include_global_docs", True):
        for gdir in loaded.data["paths"].get("global_docs", []):
            p = Path(gdir)
            if p.exists():
                sync_workspace(storage, "global", p, excludes, chunk_size, chunk_overlap)

    storage.close()
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
    print(f"Initialized CodeIndex Sync at {config_path}")
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    loaded = load_config(Path(args.config))
    set_config_value(loaded.data, args.key, parse_value(args.value))
    save_config(loaded.path, loaded.data)
    print(f"Updated {args.key}")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    config_path = Path(args.config)
    stats = _run_sync_once(config_path, workspace_override=args.workspace)
    print(json.dumps(stats, indent=2))

    if args.watch:
        print(f"Watch mode enabled. Polling every {args.interval} seconds. Ctrl+C to stop.")
        try:
            while True:
                time.sleep(args.interval)
                next_stats = _run_sync_once(config_path, workspace_override=args.workspace)
                if next_stats["indexed"] or next_stats["deleted"]:
                    print(json.dumps(next_stats, indent=2))
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
    workspaces = [workspace]
    if include_global and workspace != "global":
        workspaces.append("global")

    storage = Storage(db_path(Path(args.config).parent.resolve()))
    q_emb = embed_text(args.query)
    scored = []
    for chunk in storage.all_chunks(workspaces):
        scored.append((cosine_similarity(q_emb, chunk.embedding), chunk))
    scored.sort(key=lambda x: x[0], reverse=True)

    results = [
        {
            "workspace": c.workspace,
            "path": c.path,
            "line_start": c.line_start,
            "line_end": c.line_end,
            "score": round(score, 4),
            "snippet": c.text[:500],
        }
        for score, c in scored[:top_k]
    ]
    print(json.dumps({"query": args.query, "workspace": workspace, "results": results}, indent=2))
    storage.close()
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    storage = Storage(db_path(Path(args.config).parent.resolve()))
    counts = storage.counts()
    storage.close()
    print(json.dumps(counts, indent=2))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    storage = Storage(db_path(Path(args.config).parent.resolve()))
    print(f"Serving on {args.host}:{args.port}")
    serve(storage, args.host, args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="codeindex", description="Local-first code indexing and semantic search")
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
    p_query.set_defaults(func=cmd_query)

    p_status = sp.add_parser("status")
    p_status.set_defaults(func=cmd_status)

    p_serve = sp.add_parser("serve")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=9090)
    p_serve.set_defaults(func=cmd_serve)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
