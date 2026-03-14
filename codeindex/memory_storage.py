from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
import re
from typing import Any, Iterable

from .memory_models import CapabilitySnapshot, MemoryCitation, MemoryObservation, MemorySearchHit, MemorySession


BASE_MEMORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_sessions (
  session_id TEXT PRIMARY KEY,
  workspace TEXT NOT NULL,
  project_root TEXT NOT NULL,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  trigger_kind TEXT NOT NULL,
  command_name TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS memory_observations (
  observation_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  workspace TEXT NOT NULL,
  kind TEXT NOT NULL,
  source TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  summary TEXT NOT NULL,
  token_count INTEGER NOT NULL,
  importance REAL NOT NULL,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS memory_citations (
  citation_id TEXT PRIMARY KEY,
  observation_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  workspace TEXT NOT NULL,
  snippet TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_queue (
  queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
  observation_id TEXT NOT NULL,
  state TEXT NOT NULL,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_injection_log (
  log_id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  workspace TEXT NOT NULL,
  event TEXT NOT NULL,
  query_text TEXT NOT NULL,
  selected_layer TEXT NOT NULL,
  budget_limit INTEGER NOT NULL,
  estimated_tokens INTEGER NOT NULL,
  selected_observation_ids_json TEXT NOT NULL,
  reasons_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_capabilities (
  capability_name TEXT PRIMARY KEY,
  available INTEGER NOT NULL,
  checked_at TEXT NOT NULL,
  details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_memory_sessions_workspace ON memory_sessions(workspace, started_at);
CREATE INDEX IF NOT EXISTS idx_memory_observations_workspace ON memory_observations(workspace, created_at);
CREATE INDEX IF NOT EXISTS idx_memory_observations_session ON memory_observations(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_memory_observations_kind ON memory_observations(kind, status);
CREATE INDEX IF NOT EXISTS idx_memory_citations_observation ON memory_citations(observation_id);
CREATE INDEX IF NOT EXISTS idx_memory_queue_state ON memory_queue(state, updated_at);
CREATE INDEX IF NOT EXISTS idx_memory_injection_workspace ON memory_injection_log(workspace, created_at);
"""

FTS_MEMORY_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS memory_observation_fts USING fts5(
  observation_id UNINDEXED,
  workspace UNINDEXED,
  title,
  body,
  summary
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fts5_available(conn: sqlite3.Connection) -> bool:
    if os.getenv("CODEINDEX_DISABLE_FTS5", "").lower() in {"1", "true", "yes", "on"}:
        return False
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS __memory_fts_probe USING fts5(value)")
        conn.execute("DROP TABLE IF EXISTS __memory_fts_probe")
        return True
    except sqlite3.OperationalError:
        return False


class MemoryStorage:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.executescript(BASE_MEMORY_SCHEMA)
        self._fts5_enabled = fts5_available(conn)
        if self._fts5_enabled:
            self.conn.executescript(FTS_MEMORY_SCHEMA)

    def commit(self) -> None:
        self.conn.commit()

    @staticmethod
    def _loads(raw: str) -> dict[str, Any]:
        try:
            loaded = json.loads(raw)
        except Exception:
            return {}
        return loaded if isinstance(loaded, dict) else {}

    def record_capability(self, snapshot: CapabilitySnapshot) -> None:
        details = dict(snapshot.details)
        details["memory_search_backend"] = self.search_backend_name()
        rows = [
            ("fts5", int(snapshot.fts5_available), snapshot.checked_at, json.dumps(details, sort_keys=True)),
            ("yaml", int(snapshot.yaml_available), snapshot.checked_at, json.dumps(snapshot.details, sort_keys=True)),
        ]
        self.conn.executemany(
            "INSERT INTO memory_capabilities(capability_name,available,checked_at,details_json) VALUES(?,?,?,?) "
            "ON CONFLICT(capability_name) DO UPDATE SET available=excluded.available, checked_at=excluded.checked_at, details_json=excluded.details_json",
            rows,
        )

    def create_session(self, session: MemorySession) -> None:
        self.conn.execute(
            "INSERT INTO memory_sessions(session_id,workspace,project_root,started_at,ended_at,trigger_kind,command_name,metadata_json) VALUES(?,?,?,?,?,?,?,?)",
            (
                session.session_id,
                session.workspace,
                session.project_root,
                session.started_at,
                session.ended_at,
                session.trigger_kind,
                session.command_name,
                json.dumps(session.metadata, sort_keys=True),
            ),
        )

    def end_session(self, session_id: str, ended_at: str) -> None:
        self.conn.execute("UPDATE memory_sessions SET ended_at=? WHERE session_id=?", (ended_at, session_id))

    def add_observation(self, observation: MemoryObservation) -> None:
        self.conn.execute(
            "INSERT INTO memory_observations(observation_id,session_id,workspace,kind,source,title,body,summary,token_count,importance,created_at,status,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                observation.observation_id,
                observation.session_id,
                observation.workspace,
                observation.kind,
                observation.source,
                observation.title,
                observation.body,
                observation.summary,
                observation.token_count,
                observation.importance,
                observation.created_at,
                observation.status,
                json.dumps(observation.metadata, sort_keys=True),
            ),
        )

    def enqueue_observation(self, observation_id: str, now: str) -> None:
        self.conn.execute(
            "INSERT INTO memory_queue(observation_id,state,attempt_count,last_error,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            (observation_id, "pending", 0, None, now, now),
        )

    def claim_queue(self, max_batch_size: int, max_retries: int) -> list[tuple[int, MemoryObservation]]:
        rows = self.conn.execute(
            "SELECT q.queue_id,o.observation_id,o.session_id,o.workspace,o.kind,o.source,o.title,o.body,o.summary,o.token_count,o.importance,o.created_at,o.status,o.metadata_json "
            "FROM memory_queue q JOIN memory_observations o ON o.observation_id=q.observation_id "
            "WHERE q.state IN ('pending','failed') AND q.attempt_count < ? "
            "ORDER BY q.queue_id ASC LIMIT ?",
            (max_retries, max_batch_size),
        ).fetchall()
        claimed: list[tuple[int, MemoryObservation]] = []
        now = utc_now()
        for row in rows:
            queue_id = int(row[0])
            self.conn.execute(
                "UPDATE memory_queue SET state='processing', attempt_count=attempt_count+1, updated_at=? WHERE queue_id=?",
                (now, queue_id),
            )
            claimed.append(
                (
                    queue_id,
                    MemoryObservation(
                        observation_id=row[1],
                        session_id=row[2],
                        workspace=row[3],
                        kind=row[4],
                        source=row[5],
                        title=row[6],
                        body=row[7],
                        summary=row[8],
                        token_count=int(row[9]),
                        importance=float(row[10]),
                        created_at=row[11],
                        status=row[12],
                        metadata=self._loads(row[13]),
                    ),
                )
            )
        return claimed

    def mark_processed(
        self,
        queue_id: int,
        observation_id: str,
        summary: str,
        citation_snippet: str,
        token_count: int,
        metadata: dict[str, Any],
    ) -> None:
        now = utc_now()
        self.conn.execute(
            "UPDATE memory_queue SET state='processed', last_error=NULL, updated_at=? WHERE queue_id=?",
            (now, queue_id),
        )
        self.conn.execute(
            "UPDATE memory_observations SET summary=?, token_count=?, status='processed', metadata_json=? WHERE observation_id=?",
            (summary, token_count, json.dumps(metadata, sort_keys=True), observation_id),
        )
        row = self.conn.execute(
            "SELECT observation_id,workspace,title,body,summary FROM memory_observations WHERE observation_id=?",
            (observation_id,),
        ).fetchone()
        if row and self._fts5_enabled:
            self.conn.execute("DELETE FROM memory_observation_fts WHERE observation_id=?", (observation_id,))
            self.conn.execute(
                "INSERT INTO memory_observation_fts(observation_id,workspace,title,body,summary) VALUES(?,?,?,?,?)",
                (row[0], row[1], row[2], row[3], row[4]),
            )
        existing = self.conn.execute(
            "SELECT citation_id FROM memory_citations WHERE observation_id=? LIMIT 1",
            (observation_id,),
        ).fetchone()
        if not existing:
            citation_id = observation_id.replace("obs_", "cit_", 1)
            session_row = self.conn.execute(
                "SELECT session_id,workspace FROM memory_observations WHERE observation_id=?",
                (observation_id,),
            ).fetchone()
            if session_row:
                self.conn.execute(
                    "INSERT INTO memory_citations(citation_id,observation_id,session_id,workspace,snippet,created_at) VALUES(?,?,?,?,?,?)",
                    (citation_id, observation_id, session_row[0], session_row[1], citation_snippet[:300], now),
                )

    def mark_failed(self, queue_id: int, error: str) -> None:
        self.conn.execute(
            "UPDATE memory_queue SET state='failed', last_error=?, updated_at=? WHERE queue_id=?",
            (error, utc_now(), queue_id),
        )

    def search_observations(
        self,
        query: str,
        workspace: str,
        limit: int,
        min_importance: float,
    ) -> list[MemorySearchHit]:
        query_text = query.strip()
        if not query_text:
            rows = self.conn.execute(
                "SELECT o.observation_id,o.session_id,o.workspace,o.kind,o.source,o.title,o.body,o.summary,o.token_count,o.importance,o.created_at,o.status,o.metadata_json,"
                "c.citation_id "
                "FROM memory_observations o LEFT JOIN memory_citations c ON c.observation_id=o.observation_id "
                "WHERE o.workspace=? AND o.status='processed' AND o.importance >= ? "
                "ORDER BY o.created_at DESC LIMIT ?",
                (workspace, min_importance, limit),
            ).fetchall()
            return [self._row_to_hit(row, relevance=1.0) for row in rows]

        terms = " ".join(part for part in re.findall(r"[A-Za-z0-9_]+", query_text) if part)
        if not terms:
            return []
        if not self._fts5_enabled:
            return self._search_observations_fallback(terms, workspace, limit, min_importance)
        rows = self.conn.execute(
            "SELECT o.observation_id,o.session_id,o.workspace,o.kind,o.source,o.title,o.body,o.summary,o.token_count,o.importance,o.created_at,o.status,o.metadata_json,"
            "c.citation_id, bm25(memory_observation_fts) AS rank "
            "FROM memory_observation_fts "
            "JOIN memory_observations o ON o.observation_id=memory_observation_fts.observation_id "
            "LEFT JOIN memory_citations c ON c.observation_id=o.observation_id "
            "WHERE memory_observation_fts MATCH ? AND o.workspace=? AND o.status='processed' AND o.importance >= ? "
            "ORDER BY rank ASC, o.created_at DESC LIMIT ?",
            (terms, workspace, min_importance, limit),
        ).fetchall()
        return [self._row_to_hit(row, relevance=max(0.05, 1.0 / (1.0 + abs(float(row[14] or 0.0))))) for row in rows]

    def _search_observations_fallback(
        self,
        terms: str,
        workspace: str,
        limit: int,
        min_importance: float,
    ) -> list[MemorySearchHit]:
        term_list = [part.lower() for part in terms.split() if part]
        if not term_list:
            return []
        filters: list[str] = []
        params: list[Any] = [workspace, min_importance]
        for term in term_list:
            filters.append("(LOWER(o.title) LIKE ? OR LOWER(o.body) LIKE ? OR LOWER(o.summary) LIKE ?)")
            like_term = f"%{term}%"
            params.extend([like_term, like_term, like_term])
        sql = (
            "SELECT o.observation_id,o.session_id,o.workspace,o.kind,o.source,o.title,o.body,o.summary,o.token_count,"
            "o.importance,o.created_at,o.status,o.metadata_json,c.citation_id "
            "FROM memory_observations o "
            "LEFT JOIN memory_citations c ON c.observation_id=o.observation_id "
            "WHERE o.workspace=? AND o.status='processed' AND o.importance >= ? AND ("
            + " OR ".join(filters)
            + ")"
        )
        rows = self.conn.execute(sql, tuple(params)).fetchall()
        scored: list[tuple[float, tuple[Any, ...]]] = []
        for row in rows:
            haystacks = {
                "title": str(row[5]).lower(),
                "body": str(row[6]).lower(),
                "summary": str(row[7]).lower(),
            }
            score = 0.0
            for term in term_list:
                if term in haystacks["title"]:
                    score += 3.0
                if term in haystacks["summary"]:
                    score += 2.0
                if term in haystacks["body"]:
                    score += 1.0
            score += float(row[9]) * 0.1
            scored.append((score, row))
        scored.sort(key=lambda item: (item[0], str(item[1][10])), reverse=True)
        return [self._row_to_hit(row, relevance=max(0.05, score / max(len(term_list) * 6.0, 1.0))) for score, row in scored[:limit]]

    def _row_to_hit(self, row: tuple[Any, ...], relevance: float) -> MemorySearchHit:
        observation = MemoryObservation(
            observation_id=row[0],
            session_id=row[1],
            workspace=row[2],
            kind=row[3],
            source=row[4],
            title=row[5],
            body=row[6],
            summary=row[7],
            token_count=int(row[8]),
            importance=float(row[9]),
            created_at=row[10],
            status=row[11],
            metadata=self._loads(row[12]),
        )
        return MemorySearchHit(
            observation=observation,
            citation_id=row[13],
            relevance=relevance,
            expand_token_cost=max(observation.token_count, len(observation.body.split())),
        )

    def get_observation(self, observation_id: str) -> MemoryObservation | None:
        row = self.conn.execute(
            "SELECT observation_id,session_id,workspace,kind,source,title,body,summary,token_count,importance,created_at,status,metadata_json "
            "FROM memory_observations WHERE observation_id=?",
            (observation_id,),
        ).fetchone()
        if not row:
            return None
        return MemoryObservation(
            observation_id=row[0],
            session_id=row[1],
            workspace=row[2],
            kind=row[3],
            source=row[4],
            title=row[5],
            body=row[6],
            summary=row[7],
            token_count=int(row[8]),
            importance=float(row[9]),
            created_at=row[10],
            status=row[11],
            metadata=self._loads(row[12]),
        )

    def list_sessions(self, workspace: str, limit: int = 50) -> list[MemorySession]:
        rows = self.conn.execute(
            "SELECT session_id,workspace,project_root,started_at,ended_at,trigger_kind,command_name,metadata_json "
            "FROM memory_sessions WHERE workspace=? ORDER BY started_at DESC LIMIT ?",
            (workspace, limit),
        ).fetchall()
        return [
            MemorySession(
                session_id=row[0],
                workspace=row[1],
                project_root=row[2],
                started_at=row[3],
                ended_at=row[4],
                trigger_kind=row[5],
                command_name=row[6],
                metadata=self._loads(row[7]),
            )
            for row in rows
        ]

    def get_session(self, session_id: str) -> MemorySession | None:
        row = self.conn.execute(
            "SELECT session_id,workspace,project_root,started_at,ended_at,trigger_kind,command_name,metadata_json "
            "FROM memory_sessions WHERE session_id=?",
            (session_id,),
        ).fetchone()
        if not row:
            return None
        return MemorySession(
            session_id=row[0],
            workspace=row[1],
            project_root=row[2],
            started_at=row[3],
            ended_at=row[4],
            trigger_kind=row[5],
            command_name=row[6],
            metadata=self._loads(row[7]),
        )

    def list_citations(self, target_id: str) -> list[MemoryCitation]:
        if target_id.startswith("cit_"):
            rows = self.conn.execute(
                "SELECT citation_id,observation_id,session_id,workspace,snippet,created_at FROM memory_citations WHERE citation_id=?",
                (target_id,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT citation_id,observation_id,session_id,workspace,snippet,created_at FROM memory_citations WHERE observation_id=? ORDER BY created_at ASC",
                (target_id,),
            ).fetchall()
        return [
            MemoryCitation(
                citation_id=row[0],
                observation_id=row[1],
                session_id=row[2],
                workspace=row[3],
                snippet=row[4],
                created_at=row[5],
            )
            for row in rows
        ]

    def record_injection(
        self,
        session_id: str,
        workspace: str,
        event: str,
        query_text: str,
        selected_layer: str,
        budget_limit: int,
        estimated_tokens: int,
        selected_observation_ids: list[str],
        reasons: list[str],
    ) -> None:
        self.conn.execute(
            "INSERT INTO memory_injection_log(session_id,workspace,event,query_text,selected_layer,budget_limit,estimated_tokens,selected_observation_ids_json,reasons_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                session_id,
                workspace,
                event,
                query_text,
                selected_layer,
                budget_limit,
                estimated_tokens,
                json.dumps(selected_observation_ids),
                json.dumps(reasons),
                utc_now(),
            ),
        )

    def status(self, workspace: str) -> dict[str, Any]:
        session_count = int(self.conn.execute("SELECT COUNT(*) FROM memory_sessions WHERE workspace=?", (workspace,)).fetchone()[0])
        observation_count = int(self.conn.execute("SELECT COUNT(*) FROM memory_observations WHERE workspace=?", (workspace,)).fetchone()[0])
        citation_count = int(self.conn.execute("SELECT COUNT(*) FROM memory_citations WHERE workspace=?", (workspace,)).fetchone()[0])
        queue = self.conn.execute(
            "SELECT state, COUNT(*) FROM memory_queue GROUP BY state"
        ).fetchall()
        queue_counts = {row[0]: int(row[1]) for row in queue}
        capabilities = self.conn.execute(
            "SELECT capability_name, available, checked_at FROM memory_capabilities ORDER BY capability_name ASC"
        ).fetchall()
        capability_records = [
            {"name": row[0], "available": bool(row[1]), "checked_at": row[2]}
            for row in capabilities
        ]
        return {
            "sessions": session_count,
            "observations": observation_count,
            "citations": citation_count,
            "queue": queue_counts,
            "capabilities": {
                "memory_search_backend": self.search_backend_name(),
                "fts5_available": self._fts5_enabled,
                "degraded": not self._fts5_enabled,
                "records": capability_records,
            },
        }

    def recent_stream_events(self, workspace: str, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT observation_id,session_id,kind,source,title,summary,created_at FROM memory_observations "
            "WHERE workspace=? ORDER BY created_at DESC LIMIT ?",
            (workspace, limit),
        ).fetchall()
        return [
            {
                "observation_id": row[0],
                "session_id": row[1],
                "kind": row[2],
                "source": row[3],
                "title": row[4],
                "summary": row[5],
                "created_at": row[6],
            }
            for row in rows
        ]

    def search_backend_name(self) -> str:
        return "fts5" if self._fts5_enabled else "sql-like"
