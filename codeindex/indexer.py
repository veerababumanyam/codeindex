from __future__ import annotations

import ast
import asyncio
import fnmatch
import hashlib
import os
import re
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from .embedding import chunk_text, embed_text
from .storage import ChunkRecord, Storage

try:
    from tree_sitter_languages import get_parser as ts_get_parser  # type: ignore
except Exception:  # pragma: no cover
    ts_get_parser = None

TEXT_EXTS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".rs", ".go", ".java", ".c", ".h", ".cpp", ".hpp", ".rb", ".php", ".cs",
}

TS_LANGUAGE_BY_EXT = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
}

TS_SYMBOL_NODE_TYPES = {
    "function_definition",
    "function_declaration",
    "method_definition",
    "class_definition",
    "class_declaration",
    "interface_declaration",
    "type_alias_declaration",
    "variable_declarator",
    "lexical_declaration",
}


@dataclass
class SyncStats:
    scanned: int = 0
    indexed: int = 0
    skipped_unchanged: int = 0
    deleted: int = 0


def should_exclude(rel_path: str, excludes: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel_path, pattern) for pattern in excludes)


def is_text_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTS


def line_bounds(full_text: str, chunk: str, start_offset: int) -> tuple[int, int]:
    line_start = full_text.count("\n", 0, start_offset) + 1
    line_end = line_start + chunk.count("\n")
    return line_start, line_end


def estimate_token_count(text: str) -> int:
    return max(1, len(text.split()))


def _build_record(
    workspace: str,
    path: str,
    chunk_index: int,
    line_start: int,
    line_end: int,
    text: str,
    source_kind: str,
    symbol_name: str | None = None,
) -> ChunkRecord:
    return ChunkRecord(
        workspace=workspace,
        path=path,
        chunk_index=chunk_index,
        line_start=line_start,
        line_end=line_end,
        source_kind=source_kind,
        symbol_name=symbol_name,
        text=text,
        token_count=estimate_token_count(text),
        embedding=embed_text(text),
    )


def _ts_parser_for_suffix(suffix: str):
    if ts_get_parser is None:
        return None
    lang = TS_LANGUAGE_BY_EXT.get(suffix.lower())
    if not lang:
        return None
    try:
        return ts_get_parser(lang)
    except Exception:
        return None


def _ts_iter_nodes(root_node):
    stack = [root_node]
    while stack:
        node = stack.pop()
        yield node
        children = getattr(node, "children", [])
        if children:
            stack.extend(reversed(children))


def _ts_node_name(node, source_bytes: bytes) -> str | None:
    try:
        name_node = node.child_by_field_name("name")
    except Exception:
        name_node = None
    if name_node is not None:
        try:
            return source_bytes[name_node.start_byte : name_node.end_byte].decode("utf-8", errors="ignore").strip()
        except Exception:
            return None
    return None


def _ts_node_snippet(node, text: str) -> str:
    lines = text.splitlines()
    start = int(node.start_point[0]) + 1
    end = int(node.end_point[0]) + 1
    if 1 <= start <= len(lines):
        return "\n".join(lines[start - 1 : min(end, len(lines))])
    return ""


def extract_python_symbols(content: str) -> list[tuple[str, int, int, str]]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []

    lines = content.splitlines()
    symbols: list[tuple[str, int, int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        end_lineno = getattr(node, "end_lineno", node.lineno)
        snippet = "\n".join(lines[node.lineno - 1 : end_lineno])
        kind = "class" if isinstance(node, ast.ClassDef) else "function"
        symbols.append((f"{kind}:{node.name}", node.lineno, end_lineno, snippet))
    return symbols


def extract_symbols(path: Path, content: str) -> list[tuple[str, int, int, str]]:
    suffix = path.suffix.lower()
    if suffix == ".py":
        return extract_python_symbols(content)

    parser = _ts_parser_for_suffix(suffix)
    if parser is not None and content:
        source_bytes = content.encode("utf-8")
        tree = parser.parse(source_bytes)
        symbols: list[tuple[str, int, int, str]] = []
        for node in _ts_iter_nodes(tree.root_node):
            if not getattr(node, "is_named", False):
                continue
            if node.type not in TS_SYMBOL_NODE_TYPES:
                continue
            name = _ts_node_name(node, source_bytes) or node.type
            line_start = int(node.start_point[0]) + 1
            line_end = int(node.end_point[0]) + 1
            snippet = _ts_node_snippet(node, content)
            symbols.append((f"symbol:{name}", line_start, line_end, snippet))
        return symbols
    return []


def _process_file(
    workspace: str,
    rel_path: str,
    abs_path: str,
    chunk_size: int,
    chunk_overlap: int,
) -> tuple[str, str, list[ChunkRecord]] | None:
    path = Path(abs_path)
    try:
        raw_bytes = path.read_bytes()
    except Exception:
        return None
    if b"\x00" in raw_bytes:
        return None
    content = raw_bytes.decode("utf-8", errors="ignore")
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    chunks_raw = chunk_text(content, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunk_records: list[ChunkRecord] = []
    offset = 0
    for idx, chunk in enumerate(chunks_raw):
        found = content.find(chunk, offset)
        if found == -1:
            found = offset
        line_start, line_end = line_bounds(content, chunk, found)
        offset = found + len(chunk)
        chunk_records.append(_build_record(workspace, rel_path, idx, line_start, line_end, chunk, "chunk"))

    for sym_idx, (symbol_name, line_start, line_end, snippet) in enumerate(
        extract_symbols(path, content), start=len(chunk_records)
    ):
        chunk_records.append(
            _build_record(
                workspace,
                rel_path,
                sym_idx,
                line_start,
                line_end,
                snippet,
                "symbol",
                symbol_name=symbol_name,
            )
        )
    return rel_path, content_hash, chunk_records


async def sync_workspace(
    storage: Storage,
    workspace: str,
    root: Path,
    excludes: list[str],
    chunk_size: int,
    chunk_overlap: int,
) -> SyncStats:
    stats = SyncStats()
    existing_paths: set[str] = set()
    loop = asyncio.get_running_loop()

    process_tasks = []
    
    with ProcessPoolExecutor() as pool:
        for path in root.rglob("*"):
            if not path.is_file() or not is_text_file(path):
                continue
            rel = path.relative_to(root).as_posix()
            if should_exclude(rel, excludes):
                continue

            stats.scanned += 1
            existing_paths.add(rel)
            stat = path.stat()
            previous = await storage.file_state(workspace, rel)
            if previous is not None:
                _, previous_mtime, previous_size = previous
                if previous_mtime == stat.st_mtime and previous_size == stat.st_size:
                    stats.skipped_unchanged += 1
                    continue

            # Schedule CPU-bound work
            process_tasks.append(
                (rel, stat.st_mtime, stat.st_size, loop.run_in_executor(
                    pool, _process_file, workspace, rel, str(path.absolute()), chunk_size, chunk_overlap
                ))
            )

        for rel, mtime, size, task in process_tasks:
            result = await task
            if result is None:
                stats.skipped_unchanged += 1
                continue
            
            res_rel, content_hash, chunk_records = result
            previous = await storage.file_state(workspace, rel)
            if previous is not None and previous[0] == content_hash:
                await storage.upsert_file(workspace, rel, content_hash, mtime, size)
                stats.skipped_unchanged += 1
                continue

            await storage.upsert_file(workspace, rel, content_hash, mtime, size)
            await storage.replace_chunks(workspace, rel, chunk_records)
            stats.indexed += 1

    stats.deleted = await storage.delete_missing_files(workspace, existing_paths)
    await storage.commit()
    return stats

