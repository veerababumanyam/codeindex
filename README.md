# CodeIndex Sync

CodeIndex Sync is a lightweight, local-first CLI that incrementally indexes code and docs for low-token semantic retrieval.

## Implemented in this repository

This repository now contains a working Python prototype with:

- `codeindex init` to create `codeindex.yaml` and local index storage.
- `codeindex sync` to scan text files, chunk content, embed locally, and update a SQLite index incrementally.
- `codeindex sync --watch` to continuously poll and re-index deltas.
- `codeindex query` to return top-k semantically similar snippets scoped to a workspace (optionally with global docs).
- `codeindex status` to show index counts.
- `codeindex config` to update config keys.
- `codeindex serve` to expose `GET /search?query=...&workspace=...`.

## Architecture

### Storage

- SQLite database at `.codeindex/index.db`.
- `files` table tracks `workspace + path + content_hash + mtime` for incremental sync.
- `chunks` table stores chunk text, line bounds, and embedding vectors.

### Isolation model

- Per-project content is indexed into the selected workspace.
- Global docs are indexed into a dedicated `global` workspace.
- Queries include workspace filters and can optionally include `global`.

### Embedding model

- Default deterministic local embedding based on hashed token frequencies.
- No network dependency required for baseline indexing/query behavior.

## Quickstart

```bash
python -m codeindex.cli --config codeindex.yaml init --path /myproject --workspace myapp --global-docs /shared
python -m codeindex.cli --config codeindex.yaml sync
python -m codeindex.cli --config codeindex.yaml sync --watch --interval 2
python -m codeindex.cli --config codeindex.yaml query "find auth logic" --workspace myapp --top-k 5 --include-global
python -m codeindex.cli --config codeindex.yaml status
python -m codeindex.cli --config codeindex.yaml serve --port 9090
```

Example endpoint while serving:

```http
GET /search?query=find+auth+logic&workspace=myapp&top_k=5&include_global=true
```

## Configuration

`codeindex.yaml` is parsed/written as YAML.

See `docs/codeindex.example.yaml` for a sample config shape.
