from __future__ import annotations

import fnmatch
import hashlib
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
        content = path.read_text(encoding="utf-8", errors="ignore")
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if storage.file_hash(workspace, rel) == content_hash:
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
            chunk_records.append(
                ChunkRecord(
                    workspace=workspace,
                    path=rel,
                    chunk_index=idx,
                    line_start=line_start,
                    line_end=line_end,
                    text=chunk,
                    embedding=embed_text(chunk),
                )
            )

        storage.upsert_file(workspace, rel, content_hash, path.stat().st_mtime)
        storage.replace_chunks(workspace, rel, chunk_records)
        stats.indexed += 1

    stats.deleted = storage.delete_missing_files(workspace, existing_paths)
    storage.commit()
    return stats
