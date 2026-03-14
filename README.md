<p align="center">
  <img src="logo.png" alt="CodeIndex Logo" width="240">
</p>

# 🧠 CodeIndex

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.0.2-orange.svg)](pyproject.toml)
[![Architecture](https://img.shields.io/badge/arch-Local--First-purple.svg)](#architecture)

**CodeIndex** is like a "Search Engine & Memory" for your software code. It lives entirely on your own computer, keeping your data private while making your code understandable for AI tools.

### 🌟 What does it actually do?
Imagine your code is a massive library with thousands of books.
- **The Search Problem**: Normally, if you ask an AI "How do I log in?", it has to guess where to look. It's like a librarian who has never seen your library before.
- **The CodeIndex Solution**: CodeIndex builds a digital map of your entire library.
  - **🔍 Smart Search**: You can ask questions in plain English ("Where is the payment logic?"), and it finds the exact spot immediately.
  - **🧠 It Remembers**: It keeps a record of what you've found or analyzed before, so the AI doesn't forget context halfway through a project.
  - **💻 100% Local**: Everything happens on *your* machine. No code is ever sent to a third-party server for indexing.

---

## 📑 Table of Contents
- [✨ Core Philosophy](#-core-philosophy)
- [🚀 Key Features](#-key-features)
- [📦 Installation](#-installation)
- [🛠️ Quick Start](#-quick-start)
- [🏗️ Architecture](#-architecture)
- [🔍 Deep Intelligence (Analyze)](#-deep-intelligence-analyze)
- [🧠 Persistent Memory](#-persistent-memory)
- [🌐 Integration (API & MCP)](#-integration-api--mcp)
- [🧪 Testing](#-testing)
- [🗺️ Roadmap](#-roadmap)

---

## ✨ Core Philosophy

Standard "Code RAG" often suffers from two problems: it's too expensive (API calls) or too superficial (simple string matching). **CodeIndex** solves this by operating entirely locally with a focus on:

1.  **Precision over Noise**: Using AST-aware chunking and symbol-weighted search.
2.  **Context Continuity**: Maintaining a "Project Memory" that tracks what you've learned or discovered during a session.
3.  **Local Sovereignty**: Zero-latency, zero-cost embeddings and vector search running on your own machine via SQLite.

---

## 🚀 Key Features

### 🔍 Semantic & Hybrid Search
- **Local Vectors**: Powered by `sqlite-vec` or `sqlite-vss` for blazing-fast local similarity search.
- **Hybrid Mode**: Combines semantic meaning with exact symbol matching to ensure "find auth logic" works as well as "find `LoginController`".
- **Compact Snippets**: Returns context-stripped results to maximize token efficiency for LLM prompts.

### ⚡ Professional Code Intelligence (`analyze`)
Go beyond simple grep. Use the integrated analysis engine to query:
- **Abstract Syntax Trees (AST)**: Search for specific node types (Classes, Functions, Imports).
- **Dependency Graphs**: Map imports and relationship chains.
- **Complexity Metrics**: Identify technical debt and hotspots automatically.
- **Usage Scanning**: Find every reference to a symbol across the entire repo.

### 💾 Persistent Project Memory
The `memory_*` subsystem records your development journey.
- **Auto-Capture**: Every query and analysis is logged as a discrete "observation".
- **Progressive Disclosure**: View summaries of past interactions or expand them into full citations.
- **Session Tracking**: Organize work into coherent sessions for long-running feature implementations.

---

## 📦 Installation

### Requirements
- Python `3.10` or higher
- Windows, macOS, or Linux

### Setup
```bash
# Create and activate environment
python -m venv .venv
source .venv/bin/activate  # Or .venv\Scripts\Activate.ps1 on Windows

# Install core package
pip install -e .

# Install analysis dependencies (recommended)
pip install -e ".[analysis]"
```

---

## 🛠️ Quick Start

### 1. Initialize and Sync
Initialize your project and perform the first indexing pass.
```bash
codeindex init --path . --workspace my-project
CodeIndex --watch
```

### 2. Powerful Querying
```bash
# Semantic search
codeindex query "how is user authentication handled?" --mode hybrid

# Deep AST analysis
codeindex analyze ast --node-type ClassDef --name-contains Controller
```

### 3. Start the Intelligence Server
Expose all tools to your favorite AI agent via MCP.
```bash
codeindex serve --port 9090
```

---

## 🏗️ Architecture

CodeIndex is built as a modular pipeline that moves code from disk to an actionable memory layer.

```mermaid
graph TD
    A[Disk: Source Code] --> B[Indexer: AST & Chunks]
    B --> C[(SQLite: Index DB)]
    C --> D[Search: Semantic & Hybrid]
    C --> E[Analyze: AST & Symbols]
    D --> F[Memory: Observations & Sessions]
    E --> F
    F --> G[Client: CLI / HTTP / MCP]
```

- **Storage**: `.codeindex/index.db` (SQLite + Vectors)
- **Core modules**:
  - `indexer.py`: File system synchronization and AST parsing.
  - `storage.py`: Single-file SQLite interface for portability.
  - `memory_service.py`: Orchestrates the persistent memory lifecycle.

---

## 🔍 Deep Intelligence (Analyze)

The `analyze` command is the "scalpel" of CodeIndex. 

| Command | Purpose | Edge Case / Power Tip |
| :--- | :--- | :--- |
| `files` | List tracked project files | Use `--limit` to avoid flooding stdout. |
| `ast` | Query Python AST nodes | Filter by `node-type` or `name-contains`. |
| `symbols` | Extract signatures & docs | Perfect for generating "symbol maps" for agents. |
| `usage` | Find cross-file references | Essential for refactoring impact analysis. |
| `stats` | Project summaries | See language distribution and symbol counts. |

---

## 🧠 Persistent Memory

When you use CodeIndex, it remembers. This keeps the AI "on track" by providing a history of discovered facts.

- **Observations (`obs_...`)**: Discrete facts extracted during search.
- **Citations (`cit_...`)**: Direct links to source code backing up observations.
- **Layers**:
  - `Summary`: High-level context (low tokens).
  - `Expanded`: Detailed snippets.
  - `Full`: The complete raw observation.

---

## 🌐 Integration (API & MCP)

CodeIndex ships with a full **Model Context Protocol (MCP)** implementation. This allows LLMs (like Claude Desktop or custom agents) to use CodeIndex as a toolset.

**MCP Toolset includes:**
- `codeindex_search`: Search the codebase semantically.
- `codeindex_analyze`: Run deep structural analysis.
- `codeindex_memory_status`: Check what the project currently remembers.
- `codeindex_memory_search`: Retrieve past findings.

---

## 🧪 Testing

We value stability. Our test suite covers CLI, HTTP, and internal logic.
```bash
pytest
```
*Current test coverage includes incremental sync, memory persistence, and MCP tool serialization.*

---

## 🗺️ Roadmap

- [ ] **Filesystem Events**: Transition from polling to native `watchdog` events.
- [ ] **Multi-Language AST**: Broader support for JS/TS/Go via `tree-sitter`.
- [ ] **Web UI**: A unified dashboard for browsing the Index and Memory layers.
- [ ] **Context Pruning**: AI-driven importance scoring for memory entries.

---

## ⚖️ License

No license file is currently present. Defaulting to **All Rights Reserved** for now. Please add an `MIT` or `Apache-2.0` license before distributing publicly.

---
<p align="center">
  Built with ❤️ for the AI Generation of Developers.
</p>
