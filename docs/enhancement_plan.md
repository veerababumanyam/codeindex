# CodeIndex Enhancement Plan

This document summarizes the roadmap and technical enhancements requested for the CodeIndex project to improve its production readiness, onboarding experience, and feature set.

## 1. Documentation & Repository Setup
### Embedding Model Clarity
- **Status**: Planned
- **Details**: Clarify that CodeIndex uses a deterministic local hash-based embedding engine. This ensures:
    - **Zero Latency**: No network calls.
    - **Zero Cost**: No API fees.
    - **Privacy**: No data leaves the local machine.
    - **Hardware**: Runs efficiently on CPU (including Apple Silicon) with no GPU requirement.

### Claude Desktop MCP Integration
- **Status**: Planned
- **Details**: Provide a copy-pasteable JSON snippet for `claude_desktop_config.json`.

### Community Standards
- **Status**: Planned
- **Details**: Add `CONTRIBUTING.md`, issue templates, and PR templates to encourage open-source contributions.

## 2. Feature & Technical Enhancements
### Universal AST Support (Tree-sitter)
- **Status**: In Progress
- **Details**: The engine already integrates optional support for `tree-sitter-languages`. We will clarify that JS, TS, Go, Rust, and others are supported when this dependency is present.

### CLI Standardization
- **Status**: Planned
- **Details**: Enforce lowercase `codeindex` across all documentation for consistency.

### LLM Provider Flexibility
- **Status**: Planned
- **Details**: Ensure memory and summarization features allow users to configure Ollama, OpenAI, or Anthropic.

## 3. Distribution & Onboarding
### PyPI Distribution
- **Status**: Roadmap
- **Details**: Plan for publishing to PyPI to enable `pip install codeindex` or `uvx codeindex`.

### Dockerization
- **Status**: Planned
- **Details**: Provide a `Dockerfile` for simplified deployment without local Python environment pollution.

## 4. Project Roadmap
### Git & .gitignore Integration
- **Status**: Roadmap
- **Details**: Add support for automatically skipping files based on `.gitignore` and prioritizing recently changed files via Git diff analysis.
