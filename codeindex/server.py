from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .embedding import cosine_similarity, embed_text
from .storage import Storage


class SearchHandler(BaseHTTPRequestHandler):
    storage: Storage

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/search":
            self.send_error(404, "Not Found")
            return
        params = parse_qs(parsed.query)
        query = params.get("query", [""])[0]
        workspace = params.get("workspace", [""])[0]
        include_global = params.get("include_global", ["true"])[0].lower() == "true"
        try:
            top_k = max(1, int(params.get("top_k", ["5"])[0]))
        except ValueError:
            self.send_error(400, "top_k must be an integer")
            return

        if not query or not workspace:
            self.send_error(400, "query and workspace are required")
            return

        workspaces = [workspace]
        if include_global and workspace != "global":
            workspaces.append("global")

        q_emb = embed_text(query)
        scored = []
        for chunk in self.storage.all_chunks(workspaces):
            score = cosine_similarity(q_emb, chunk.embedding)
            scored.append((score, chunk))
        scored.sort(key=lambda x: x[0], reverse=True)

        payload = {
            "query": query,
            "workspace": workspace,
            "results": [
                {
                    "workspace": c.workspace,
                    "path": c.path,
                    "line_start": c.line_start,
                    "line_end": c.line_end,
                    "score": round(score, 4),
                    "snippet": c.text[:500],
                }
                for score, c in scored[:top_k]
            ],
        }

        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve(storage: Storage, host: str, port: int) -> None:
    class Handler(SearchHandler):
        pass

    Handler.storage = storage
    server = ThreadingHTTPServer((host, port), Handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()
