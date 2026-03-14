from __future__ import annotations

import ast
import fnmatch
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .embedding import chunk_text, embed_text
from .storage import ChunkRecord, Storage

TEXT_EXTS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".rs", ".go", ".java", ".c", ".h", ".cpp", ".hpp", ".rb", ".php", ".cs",
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


SYMBOL_PATTERNS = {
    ".js": [
        re.compile(r"^\s*(?:export\s+)?function\s+([A-Za-z_][\w$]*)"),
        re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z_][\w$]*)"),
        re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_][\w$]*)\s*=\s*(?:async\s*)?\("),
    ],
    ".jsx": [
        re.compile(r"^\s*(?:export\s+)?function\s+([A-Za-z_][\w$]*)"),
        re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z_][\w$]*)"),
        re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_][\w$]*)\s*=\s*(?:async\s*)?\("),
    ],
    ".ts": [
        re.compile(r"^\s*(?:export\s+)?function\s+([A-Za-z_][\w$]*)"),
        re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z_][\w$]*)"),
        re.compile(r"^\s*(?:export\s+)?(?:const|let)\s+([A-Za-z_][\w$]*)\s*=\s*(?:async\s*)?\("),
    ],
    ".tsx": [
        re.compile(r"^\s*(?:export\s+)?function\s+([A-Za-z_][\w$]*)"),
        re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z_][\w$]*)"),
        re.compile(r"^\s*(?:export\s+)?(?:const|let)\s+([A-Za-z_][\w$]*)\s*=\s*(?:async\s*)?\("),
    ],
    ".go": [
        re.compile(r"^\s*func\s+([A-Za-z_]\w*)"),
        re.compile(r"^\s*type\s+([A-Za-z_]\w*)\s+struct"),
    ],
}


def extract_regex_symbols(content: str, suffix: str) -> list[tuple[str, int, int, str]]:
    patterns = SYMBOL_PATTERNS.get(suffix, [])
    if not patterns:
        return []

    lines = content.splitlines()
    symbols: list[tuple[str, int, int, str]] = []
    for idx, line in enumerate(lines, start=1):
        for pattern in patterns:
            match = pattern.match(line)
            if not match:
                continue
            end = min(len(lines), idx + 11)
            snippet = "\n".join(lines[idx - 1 : end])
            symbols.append((f"symbol:{match.group(1)}", idx, end, snippet))
            break
    return symbols


def extract_symbols(path: Path, content: str) -> list[tuple[str, int, int, str]]:
    if path.suffix.lower() == ".py":
        return extract_python_symbols(content)
    return extract_regex_symbols(content, path.suffix.lower())


def sync_workspace(
    storage: Storage,
    workspace: str,
    root: Path,
    excludes: list[str],
    chunk_size: int,
    chunk_overlap: int,
) -> SyncStats:
    stats = SyncStats()
    existing_paths: set[str] = set()

    for path in root.rglob("*"):
        if not path.is_file() or not is_text_file(path):
            continue
        rel = path.relative_to(root).as_posix()
        if should_exclude(rel, excludes):
            continue

        stats.scanned += 1
        existing_paths.add(rel)
        stat = path.stat()
        previous = storage.file_state(workspace, rel)
        if previous is not None:
            _, previous_mtime, previous_size = previous
            if previous_mtime == stat.st_mtime and previous_size == stat.st_size:
                stats.skipped_unchanged += 1
                continue

        raw_bytes = path.read_bytes()
        if b"\x00" in raw_bytes:
            stats.skipped_unchanged += 1
            continue
        content = raw_bytes.decode("utf-8", errors="ignore")
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if previous is not None and previous[0] == content_hash:
            storage.upsert_file(workspace, rel, content_hash, stat.st_mtime, stat.st_size)
            stats.skipped_unchanged += 1
            continue

        chunks_raw = chunk_text(content, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        chunk_records: list[ChunkRecord] = []
        offset = 0
        for idx, chunk in enumerate(chunks_raw):
            found = content.find(chunk, offset)
            if found == -1:
                found = offset
            line_start, line_end = line_bounds(content, chunk, found)
            offset = found + len(chunk)
            chunk_records.append(_build_record(workspace, rel, idx, line_start, line_end, chunk, "chunk"))

        for sym_idx, (symbol_name, line_start, line_end, snippet) in enumerate(extract_symbols(path, content), start=len(chunk_records)):
            chunk_records.append(
                _build_record(
                    workspace,
                    rel,
                    sym_idx,
                    line_start,
                    line_end,
                    snippet,
                    "symbol",
                    symbol_name=symbol_name,
                )
            )

        storage.upsert_file(workspace, rel, content_hash, stat.st_mtime, stat.st_size)
        storage.replace_chunks(workspace, rel, chunk_records)
        stats.indexed += 1

    stats.deleted = storage.delete_missing_files(workspace, existing_paths)
    storage.commit()
    return stats
