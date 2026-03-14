import sqlite3

from codeindex.memory_models import MemoryObservation
from codeindex.memory_storage import MemoryStorage, utc_now


def test_memory_storage_degrades_cleanly_without_fts5(monkeypatch):
    monkeypatch.setenv("CODEINDEX_DISABLE_FTS5", "1")
    conn = sqlite3.connect(":memory:")
    storage = MemoryStorage(conn)

    observation = MemoryObservation(
        observation_id="obs_1",
        session_id="sess_1",
        workspace="demo",
        kind="event",
        source="test",
        title="Authentication flow",
        body="authenticate token refresh fallback",
        summary="authenticate summary",
        token_count=4,
        importance=0.9,
        created_at=utc_now(),
        status="raw",
        metadata={},
    )
    storage.add_observation(observation)
    storage.mark_processed(
        queue_id=1,
        observation_id="obs_1",
        summary="authenticate summary",
        citation_snippet="authenticate summary",
        token_count=4,
        metadata={},
    )

    hits = storage.search_observations("authenticate", "demo", limit=5, min_importance=0.0)
    assert hits
    assert hits[0].observation.observation_id == "obs_1"

    status = storage.status("demo")
    assert status["capabilities"]["memory_search_backend"] == "sql-like"
    assert status["capabilities"]["fts5_available"] is False
    assert status["capabilities"]["degraded"] is True

    try:
        conn.execute("SELECT COUNT(*) FROM memory_observation_fts")
    except sqlite3.OperationalError:
        pass
    else:
        raise AssertionError("memory_observation_fts should not exist when FTS5 is disabled")
