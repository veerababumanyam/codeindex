from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
  workspace TEXT NOT NULL,
  path TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  mtime REAL NOT NULL,
  PRIMARY KEY (workspace, path)
);

CREATE TABLE IF NOT EXISTS chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  workspace TEXT NOT NULL,
  path TEXT NOT NULL,
  chunk_index INTEGER NOT NULL,
  line_start INTEGER NOT NULL,
  line_end INTEGER NOT NULL,
  text TEXT NOT NULL,
  embedding TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chunks_workspace ON chunks(workspace);
"""


@dataclass
class ChunkRecord:
    workspace: str
    path: str
    chunk_index: int
    line_start: int
    line_end: int
    text: str
    embedding: list[float]


class Storage:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def file_hash(self, workspace: str, path: str) -> str | None:
        row = self.conn.execute(
            "SELECT content_hash FROM files WHERE workspace=? AND path=?", (workspace, path)
        ).fetchone()
        return row[0] if row else None

    def upsert_file(self, workspace: str, path: str, content_hash: str, mtime: float) -> None:
        self.conn.execute(
            "INSERT INTO files(workspace,path,content_hash,mtime) VALUES(?,?,?,?) "
            "ON CONFLICT(workspace,path) DO UPDATE SET content_hash=excluded.content_hash, mtime=excluded.mtime",
            (workspace, path, content_hash, mtime),
        )

    def replace_chunks(self, workspace: str, path: str, chunks: Iterable[ChunkRecord]) -> None:
        self.conn.execute("DELETE FROM chunks WHERE workspace=? AND path=?", (workspace, path))
        self.conn.executemany(
            "INSERT INTO chunks(workspace,path,chunk_index,line_start,line_end,text,embedding) VALUES(?,?,?,?,?,?,?)",
            [
                (
                    c.workspace,
                    c.path,
                    c.chunk_index,
                    c.line_start,
                    c.line_end,
                    c.text,
                    json.dumps(c.embedding),
                )
                for c in chunks
            ],
        )

    def delete_missing_files(self, workspace: str, existing_paths: set[str]) -> int:
        rows = self.conn.execute("SELECT path FROM files WHERE workspace=?", (workspace,)).fetchall()
        deleted = 0
        for (path,) in rows:
            if path not in existing_paths:
                self.conn.execute("DELETE FROM files WHERE workspace=? AND path=?", (workspace, path))
                self.conn.execute("DELETE FROM chunks WHERE workspace=? AND path=?", (workspace, path))
                deleted += 1
        return deleted

    def all_chunks(self, workspaces: list[str]) -> list[ChunkRecord]:
        placeholders = ",".join("?" for _ in workspaces)
        rows = self.conn.execute(
            f"SELECT workspace,path,chunk_index,line_start,line_end,text,embedding FROM chunks WHERE workspace IN ({placeholders})",
            tuple(workspaces),
        ).fetchall()
        return [
            ChunkRecord(
                workspace=r[0],
                path=r[1],
                chunk_index=r[2],
                line_start=r[3],
                line_end=r[4],
                text=r[5],
                embedding=json.loads(r[6]),
            )
            for r in rows
        ]

    def counts(self) -> dict[str, int]:
        files = self.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        chunks = self.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        workspaces = self.conn.execute("SELECT COUNT(DISTINCT workspace) FROM files").fetchone()[0]
        return {"files": files, "chunks": chunks, "workspaces": workspaces}

    def commit(self) -> None:
        self.conn.commit()
