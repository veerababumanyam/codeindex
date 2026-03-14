from __future__ import annotations

import json
from html import escape


def render_viewer_page(workspace: str) -> bytes:
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CodeIndex Memory Viewer</title>
  <style>
    :root {{
      --bg: #f4efe7;
      --panel: #fffaf2;
      --ink: #1f1a17;
      --muted: #675d56;
      --accent: #ba5b31;
      --line: #dfd1c4;
    }}
    body {{ margin: 0; font-family: Georgia, 'Times New Roman', serif; background: linear-gradient(135deg, #f8f4ec, #efe2d0); color: var(--ink); }}
    header {{ padding: 24px; border-bottom: 1px solid var(--line); }}
    h1 {{ margin: 0 0 4px; font-size: 28px; }}
    .wrap {{ display: grid; grid-template-columns: 320px 1fr; gap: 16px; padding: 16px; }}
    .panel {{ background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 16px; box-shadow: 0 8px 30px rgba(64, 44, 27, 0.08); }}
    .events {{ display: grid; gap: 12px; max-height: 72vh; overflow: auto; }}
    .event {{ border: 1px solid var(--line); border-radius: 12px; padding: 12px; background: rgba(255,255,255,0.7); }}
    .meta {{ color: var(--muted); font-size: 12px; }}
    input, button {{ font: inherit; }}
    input {{ width: 100%; padding: 10px 12px; border-radius: 10px; border: 1px solid var(--line); margin-bottom: 12px; }}
    button {{ border: 0; background: var(--accent); color: white; padding: 10px 14px; border-radius: 999px; cursor: pointer; }}
    pre {{ white-space: pre-wrap; word-break: break-word; font-family: Consolas, monospace; font-size: 12px; }}
    @media (max-width: 900px) {{ .wrap {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <header>
    <h1>Persistent Memory Viewer</h1>
    <div class="meta">Workspace: {escape(workspace)} | Real-time stream + search</div>
  </header>
  <div class="wrap">
    <section class="panel">
      <input id="query" placeholder="Search memory">
      <button id="searchBtn">Search</button>
      <div id="searchResults" class="events" style="margin-top:16px;"></div>
    </section>
    <section class="panel">
      <div id="events" class="events"></div>
    </section>
  </div>
  <script>
    const workspace = {json.dumps(workspace)};
    const eventsEl = document.getElementById('events');
    const searchResultsEl = document.getElementById('searchResults');
    function appendText(parent, tagName, className, value) {{
      const el = document.createElement(tagName);
      if (className) el.className = className;
      el.textContent = value || '';
      parent.appendChild(el);
    }}
    function renderCard(target, item) {{
      const el = document.createElement('div');
      el.className = 'event';
      appendText(el, 'strong', '', item.title || item.kind || item.observation_id || '');
      appendText(
        el,
        'div',
        'meta',
        `${{item.created_at || ''}}${{item.citation_id ? ' | ' + item.citation_id : ''}}`
      );
      appendText(el, 'div', '', item.summary || item.snippet || '');
      target.prepend(el);
    }}
    async function loadSearch() {{
      searchResultsEl.innerHTML = '';
      const query = document.getElementById('query').value;
      const resp = await fetch(`/memory/search?workspace=${{encodeURIComponent(workspace)}}&query=${{encodeURIComponent(query)}}`);
      const payload = await resp.json();
      for (const item of payload.results || []) renderCard(searchResultsEl, item);
    }}
    document.getElementById('searchBtn').addEventListener('click', loadSearch);
    const source = new EventSource(`/memory/stream?workspace=${{encodeURIComponent(workspace)}}`);
    source.onmessage = (event) => {{
      const payload = JSON.parse(event.data);
      for (const item of payload.events || []) renderCard(eventsEl, item);
    }};
  </script>
</body>
</html>
"""
    return html.encode("utf-8")


def render_stream_payload(events: list[dict[str, object]]) -> bytes:
    return f"data: {json.dumps({'events': events})}\n\n".encode("utf-8")
