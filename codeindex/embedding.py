from __future__ import annotations

import hashlib
import math
import re
from typing import Iterable, List

TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# Global fastembed model placeholder
_FASTEMBED_MODEL = None
_ADVANCED_MODE = False

def enable_advanced_mode():
    global _FASTEMBED_MODEL, _ADVANCED_MODE
    _ADVANCED_MODE = True
    try:
        from fastembed import TextEmbedding
        if _FASTEMBED_MODEL is None:
            # We use a lightweight local model
            _FASTEMBED_MODEL = TextEmbedding("BAAI/bge-small-en-v1.5")
    except ImportError:
        raise RuntimeError("fastembed is not installed. Install with `pip install codeindex-sync[advanced]`")

def get_embedding_dimensions() -> int:
    return 384 if _ADVANCED_MODE else 64

def tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]

def embed_text(text: str, dims: int = 64) -> list[float]:
    if _ADVANCED_MODE and _FASTEMBED_MODEL is not None:
        try:
            embeddings = list(_FASTEMBED_MODEL.embed([text]))
            if embeddings:
                return [float(x) for x in embeddings[0]]
        except Exception:
            pass # Fallback to 0s if something fails
        return [0.0] * 384

    # Deterministic local embedding via hashed token frequencies.
    vec = [0.0] * dims
    for tok in tokenize(text):
        digest = hashlib.sha256(tok.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dims
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return vec
    return [v / norm for v in vec]

def cosine_similarity(a: Iterable[float], b: Iterable[float]) -> float:
    a_list = list(a)
    b_list = list(b)
    if len(a_list) != len(b_list):
        raise ValueError("Vector dimensions must match")
    return sum(x * y for x, y in zip(a_list, b_list))

def chunk_text(text: str, chunk_size: int = 800, chunk_overlap: int = 120) -> List[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be >= 0 and < chunk_size")

    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    step = chunk_size - chunk_overlap
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start += step
    return chunks
