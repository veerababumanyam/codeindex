from __future__ import annotations

import json

from .memory_models import MemoryObservation
from .memory_storage import MemoryStorage


def _short_summary(observation: MemoryObservation) -> str:
    if observation.summary:
        return observation.summary
    body = observation.body.strip()
    if len(body) <= 220:
        return body
    return body[:217] + "..."


async def process_pending_observations(storage: MemoryStorage, max_batch_size: int, max_retries: int) -> dict[str, int]:
    claimed = await storage.claim_queue(max_batch_size=max_batch_size, max_retries=max_retries)
    processed = 0
    failed = 0
    for queue_id, observation in claimed:
        try:
            metadata = dict(observation.metadata)
            metadata.setdefault("expanded_summary", observation.summary or _short_summary(observation))
            snippet = observation.summary or _short_summary(observation)
            await storage.mark_processed(
                queue_id=queue_id,
                observation_id=observation.observation_id,
                summary=_short_summary(observation),
                citation_snippet=snippet,
                token_count=max(1, len((observation.body or "").split())),
                metadata=metadata,
            )
            processed += 1
        except Exception as exc:  # pragma: no cover - defensive
            await storage.mark_failed(queue_id=queue_id, error=str(exc))
            failed += 1
    if claimed:
        await storage.commit()
    return {"processed": processed, "failed": failed, "claimed": len(claimed)}
