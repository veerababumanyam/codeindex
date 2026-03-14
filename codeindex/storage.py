from __future__ import annotations

from array import array
import json
import os
import aiosqlite
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, AsyncIterator

from .memory_storage import MemoryStorage

try:
    import sqlite_vec  # type: ignore
except Exception:  # pragma: no cover - optional runtime capability
    sqlite_vec = None

try:
    import sqlite_vss  # type: ignore
except Exception:  # pragma: no cover - optional runtime capability
    sqlite_vss = None


SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
  workspace TEXT NOT NULL,
  path TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  mtime REAL NOT NULL,
  size INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (workspace, path)
);

CREATE TABLE IF NOT EXISTS chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  workspace TEXT NOT NULL,
  path TEXT NOT NULL,
  chunk_index INTEGER NOT NULL,
  line_start INTEGER NOT NULL,
  line_end INTEGER NOT NULL,
  source_kind TEXT NOT NULL DEFAULT 'chunk',
  symbol_name TEXT,
  text TEXT NOT NULL,
  token_count INTEGER NOT NULL DEFAULT 0,
  embedding BLOB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chunks_workspace ON chunks(workspace);
CREATE INDEX IF NOT EXISTS idx_chunks_kind ON chunks(workspace, source_kind);
"""


@dataclass
class ChunkRecord:
    workspace: str
    path: str
    chunk_index: int
    line_start: int
    line_end: int
    source_kind: str
    symbol_name: str | None
    text: str
    token_count: int
    embedding: list[float]


class Storage:
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self.conn = conn
        self._vector_backend = "python-cosine"

    @classmethod
    async def create(cls, db_path: Path) -> Storage:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(str(db_path))
        storage = cls(conn)
        await storage._try_enable_vector_extension()
        await storage.conn.executescript(SCHEMA)
        await MemoryStorage.create(storage.conn)
        await storage._migrate_schema()
        await storage._sync_vec_index()
        await storage.conn.commit()
        return storage

    async def _try_enable_vector_extension(self) -> None:
        if os.getenv("CODEINDEX_DISABLE_VECTORS", "").lower() in {"1", "true", "yes", "on"}:
            self._vector_backend = "python-cosine"
            return
        if await self._try_enable_sqlite_vec():
            self._vector_backend = "sqlite-vec"
            return
        if await self._try_enable_sqlite_vss():
            self._vector_backend = "sqlite-vss"
            return
        self._vector_backend = "python-cosine"

    async def _try_enable_sqlite_vec(self) -> bool:
        if sqlite_vec is None:
            return False
        try:
            await self.conn.enable_load_extension(True)
            await self.conn.run(sqlite_vec.load)
            await self.conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vec USING vec0(embedding float[64])")
            return True
        except Exception:
            return False
        finally:
            try:
                await self.conn.enable_load_extension(False)
            except Exception:
                pass

    async def _try_enable_sqlite_vss(self) -> bool:
        if sqlite_vss is None:
            return False
        try:
            await self.conn.enable_load_extension(True)
            await self.conn.run(sqlite_vss.load)
            await self.conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vss USING vss0(embedding(64))")
            return True
        except Exception:
            return False
        finally:
            try:
                await self.conn.enable_load_extension(False)
            except Exception:
                pass

    async def _migrate_schema(self) -> None:
        async with self.conn.execute("PRAGMA table_info(chunks)") as cursor:
            rows = await cursor.fetchall()
        columns = {row[1] for row in rows}
        if "source_kind" not in columns:
            await self.conn.execute("ALTER TABLE chunks ADD COLUMN source_kind TEXT NOT NULL DEFAULT 'chunk'")
        if "symbol_name" not in columns:
            await self.conn.execute("ALTER TABLE chunks ADD COLUMN symbol_name TEXT")
        if "token_count" not in columns:
            await self.conn.execute("ALTER TABLE chunks ADD COLUMN token_count INTEGER NOT NULL DEFAULT 0")
        
        async with self.conn.execute("PRAGMA table_info(files)") as cursor:
            file_rows = await cursor.fetchall()
        file_columns = {row[1] for row in file_rows}
        if "size" not in file_columns:
            await self.conn.execute("ALTER TABLE files ADD COLUMN size INTEGER NOT NULL DEFAULT 0")
        await self.conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_kind ON chunks(workspace, source_kind)")

    async def _sync_vec_index(self) -> None:
        if not self.supports_vector_search():
            return
        async with self.conn.execute("SELECT COUNT(*) FROM chunks") as cursor:
            row = await cursor.fetchone()
            chunk_count = int(row[0]) if row else 0
        
        vector_table = "chunk_vec" if self._vector_backend == "sqlite-vec" else "chunk_vss"
        async with self.conn.execute(f"SELECT COUNT(*) FROM {vector_table}") as cursor:
            row = await cursor.fetchone()
            vec_count = int(row[0]) if row else 0
            
        if chunk_count == vec_count:
            return
        await self.conn.execute(f"DELETE FROM {vector_table}")
        async with self.conn.execute("SELECT id, embedding FROM chunks") as cursor:
            rows = await cursor.fetchall()
        for chunk_id, raw_embedding in rows:
            vector_value = self._vector_value(raw_embedding)
            await self.conn.execute(f"INSERT INTO {vector_table}(rowid, embedding) VALUES(?, ?)", (chunk_id, vector_value))

    async def close(self) -> None:
        await self.conn.close()

    async def __aenter__(self) -> Storage:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    @staticmethod
    def _encode_embedding(embedding: list[float]) -> bytes:
        return array("f", embedding).tobytes()

    @staticmethod
    def _decode_embedding(raw: bytes | str) -> list[float]:
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [float(v) for v in parsed]
            except Exception:
                pass
            decoded = array("f")
            decoded.frombytes(bytes.fromhex(raw))
            return decoded.tolist()
        decoded = array("f")
        decoded.frombytes(raw)
        return decoded.tolist()

    @staticmethod
    def _decode_embedding_blob(raw: bytes | memoryview) -> list[float]:
        decoded = array("f")
        decoded.frombytes(bytes(raw))
        return decoded.tolist()

    def supports_vector_search(self) -> bool:
        return self._vector_backend in {"sqlite-vec", "sqlite-vss"}

    def vector_backend_name(self) -> str:
        return self._vector_backend

    def capability_summary(self) -> dict[str, object]:
        accelerated = self.supports_vector_search()
        return {
            "backend": self._vector_backend,
            "accelerated": accelerated,
            "degraded": not accelerated,
        }

    def _vector_value(self, embedding_or_raw: list[float] | bytes | bytearray | memoryview | str) -> object:
        if self._vector_backend == "sqlite-vss":
            if isinstance(embedding_or_raw, list):
                return json.dumps(embedding_or_raw)
            return json.dumps(self._decode_embedding(embedding_or_raw))
        if isinstance(embedding_or_raw, list):
            return self._encode_embedding(embedding_or_raw)
        if isinstance(embedding_or_raw, (bytes, bytearray, memoryview)):
            return bytes(embedding_or_raw)
        return self._encode_embedding(self._decode_embedding(embedding_or_raw))

    async def file_state(self, workspace: str, path: str) -> tuple[str, float, int] | None:
        async with self.conn.execute(
            "SELECT content_hash, mtime, size FROM files WHERE workspace=? AND path=?",
            (workspace, path),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        return row[0], float(row[1]), int(row[2])

    async def upsert_file(self, workspace: str, path: str, content_hash: str, mtime: float, size: int) -> None:
        await self.conn.execute(
            "INSERT INTO files(workspace,path,content_hash,mtime,size) VALUES(?,?,?,?,?) "
            "ON CONFLICT(workspace,path) DO UPDATE SET content_hash=excluded.content_hash, mtime=excluded.mtime, size=excluded.size",
            (workspace, path, content_hash, mtime, size),
        )

    async def replace_chunks(self, workspace: str, path: str, chunks: Iterable[ChunkRecord]) -> None:
        async with self.conn.execute(
            "SELECT id FROM chunks WHERE workspace=? AND path=?",
            (workspace, path),
        ) as cursor:
            rows = await cursor.fetchall()
        old_ids = [row[0] for row in rows]
        
        await self.conn.execute("DELETE FROM chunks WHERE workspace=? AND path=?", (workspace, path))
        if self.supports_vector_search() and old_ids:
            placeholders = ",".join("?" for _ in old_ids)
            vector_table = "chunk_vec" if self._vector_backend == "sqlite-vec" else "chunk_vss"
            await self.conn.execute(f"DELETE FROM {vector_table} WHERE rowid IN ({placeholders})", tuple(old_ids))

        for c in chunks:
            async with self.conn.execute(
                "INSERT INTO chunks(workspace,path,chunk_index,line_start,line_end,source_kind,symbol_name,text,token_count,embedding) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    c.workspace,
                    c.path,
                    c.chunk_index,
                    c.line_start,
                    c.line_end,
                    c.source_kind,
                    c.symbol_name,
                    c.text,
                    c.token_count,
                    self._encode_embedding(c.embedding),
                ),
            ) as cursor:
                lastrowid = cursor.lastrowid
            
            if self.supports_vector_search():
                vector_table = "chunk_vec" if self._vector_backend == "sqlite-vec" else "chunk_vss"
                await self.conn.execute(
                    f"INSERT INTO {vector_table}(rowid, embedding) VALUES(?, ?)",
                    (lastrowid, self._vector_value(c.embedding)),
                )

    async def delete_missing_files(self, workspace: str, existing_paths: set[str]) -> int:
        async with self.conn.execute("SELECT path FROM files WHERE workspace=?", (workspace,)) as cursor:
            rows = await cursor.fetchall()
        deleted = 0
        for (path,) in rows:
            if path not in existing_paths:
                await self.conn.execute("DELETE FROM files WHERE workspace=? AND path=?", (workspace, path))
                if self.supports_vector_search():
                    async with self.conn.execute(
                        "SELECT id FROM chunks WHERE workspace=? AND path=?",
                        (workspace, path),
                    ) as cursor:
                        chunk_rows = await cursor.fetchall()
                    chunk_ids = [row[0] for row in chunk_rows]
                    if chunk_ids:
                        placeholders = ",".join("?" for _ in chunk_ids)
                        vector_table = "chunk_vec" if self._vector_backend == "sqlite-vec" else "chunk_vss"
                        await self.conn.execute(f"DELETE FROM {vector_table} WHERE rowid IN ({placeholders})", tuple(chunk_ids))
                await self.conn.execute("DELETE FROM chunks WHERE workspace=? AND path=?", (workspace, path))
                deleted += 1
        return deleted

    async def vector_search(
        self,
        workspaces: list[str],
        source_kinds: list[str],
        query_embedding: list[float],
        top_k: int,
        query_terms: list[str] | None = None,
    ) -> list[tuple[ChunkRecord, float]]:
        if not self.supports_vector_search():
            return []

        workspace_placeholders = ",".join("?" for _ in workspaces)
        kind_placeholders = ",".join("?" for _ in source_kinds)
        if self._vector_backend == "sqlite-vss":
            sql = (
                "WITH nearest AS ("
                "  SELECT rowid, distance "
                "  FROM chunk_vss "
                "  WHERE vss_search(embedding, ?) "
                "  LIMIT ?"
                ") "
                "SELECT c.workspace,c.path,c.chunk_index,c.line_start,c.line_end,c.source_kind,c.symbol_name,c.text,c.token_count,c.embedding,nearest.distance "
                "FROM nearest "
                "JOIN chunks c ON c.id = nearest.rowid "
                f"WHERE c.workspace IN ({workspace_placeholders}) "
                f"AND c.source_kind IN ({kind_placeholders})"
            )
            params: list[object] = [self._vector_value(query_embedding), top_k]
        else:
            sql = (
                "WITH nearest AS ("
                "  SELECT rowid, distance "
                "  FROM chunk_vec "
                "  WHERE embedding MATCH ? AND k = ?"
                ") "
                "SELECT c.workspace,c.path,c.chunk_index,c.line_start,c.line_end,c.source_kind,c.symbol_name,c.text,c.token_count,c.embedding,nearest.distance "
                "FROM nearest "
                "JOIN chunks c ON c.id = nearest.rowid "
                f"WHERE c.workspace IN ({workspace_placeholders}) "
                f"AND c.source_kind IN ({kind_placeholders})"
            )
            params = [self._vector_value(query_embedding), top_k]
        params.extend(workspaces)
        params.extend(source_kinds)

        if query_terms:
            filters: list[str] = []
            for term in query_terms:
                filters.append("(LOWER(c.text) LIKE ? OR LOWER(COALESCE(c.symbol_name, '')) LIKE ?)")
                like_term = f"%{term}%"
                params.extend([like_term, like_term])
            sql += " AND (" + " OR ".join(filters) + ")"

        sql += " ORDER BY nearest.distance ASC"
        async with self.conn.execute(sql, tuple(params)) as cursor:
            rows = await cursor.fetchall()
        return [
            (
                ChunkRecord(
                    workspace=r[0],
                    path=r[1],
                    chunk_index=r[2],
                    line_start=r[3],
                    line_end=r[4],
                    source_kind=r[5],
                    symbol_name=r[6],
                    text=r[7],
                    token_count=r[8],
                    embedding=self._decode_embedding_blob(r[9]),
                ),
                float(r[10]),
            )
            for r in rows
        ]

    async def stream_chunks(
        self,
        workspaces: list[str],
        source_kinds: list[str] | None = None,
        query_terms: list[str] | None = None,
    ) -> AsyncIterator[ChunkRecord]:
        placeholders = ",".join("?" for _ in workspaces)
        params: list[str] = list(workspaces)
        query = (
            "SELECT workspace,path,chunk_index,line_start,line_end,source_kind,symbol_name,text,token_count,embedding "
            f"FROM chunks WHERE workspace IN ({placeholders})"
        )
        if source_kinds:
            kind_placeholders = ",".join("?" for _ in source_kinds)
            query += f" AND source_kind IN ({kind_placeholders})"
            params.extend(source_kinds)
        if query_terms:
            filters: list[str] = []
            for term in query_terms:
                filters.append("(LOWER(text) LIKE ? OR LOWER(COALESCE(symbol_name, '')) LIKE ?)")
                like_term = f"%{term}%"
                params.extend([like_term, like_term])
            query += " AND (" + " OR ".join(filters) + ")"
        
        async with self.conn.execute(query, tuple(params)) as cursor:
            async for r in cursor:
                yield ChunkRecord(
                    workspace=r[0],
                    path=r[1],
                    chunk_index=r[2],
                    line_start=r[3],
                    line_end=r[4],
                    source_kind=r[5],
                    symbol_name=r[6],
                    text=r[7],
                    token_count=r[8],
                    embedding=self._decode_embedding(r[9]),
                )

    async def counts(self) -> dict[str, int]:
        async with self.conn.execute("SELECT COUNT(*) FROM files") as cursor:
            row = await cursor.fetchone()
            files = row[0] if row else 0
        async with self.conn.execute("SELECT COUNT(*) FROM chunks") as cursor:
            row = await cursor.fetchone()
            chunks = row[0] if row else 0
        async with self.conn.execute("SELECT COUNT(*) FROM chunks WHERE source_kind='symbol'") as cursor:
            row = await cursor.fetchone()
            symbols = row[0] if row else 0
        async with self.conn.execute("SELECT COUNT(DISTINCT workspace) FROM files") as cursor:
            row = await cursor.fetchone()
            workspaces = row[0] if row else 0
        return {"files": files, "chunks": chunks, "symbols": symbols, "workspaces": workspaces}

    async def workspace_token_count(self, workspaces: list[str]) -> int:
        placeholders = ",".join("?" for _ in workspaces)
        async with self.conn.execute(
            f"SELECT COALESCE(SUM(token_count), 0) FROM chunks WHERE workspace IN ({placeholders}) AND source_kind='chunk'",
            tuple(workspaces),
        ) as cursor:
            row = await cursor.fetchone()
        return int(row[0] or 0) if row else 0

    async def commit(self) -> None:
        await self.conn.commit()
